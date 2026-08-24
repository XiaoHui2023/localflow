from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import AuthManager
from .config_repository import ConfigConflict, ConfigRepository
from .executor import SubprocessExecutor, SystemdExecutor
from .models import BatchCreate, TaskCreate, TaskRecord
from .plugins import PluginRegistry
from .service import TaskService
from .settings import Settings, initialize_root, load_settings
from .storage import Store
from .time_service import TimeService
from .variables import VariableError, VariableResolver
from .watcher import DirectoryWatcher


class LocalLogin(BaseModel):
    code: str


class ConfigWrite(BaseModel):
    content: str


class TimeAdjustment(BaseModel):
    reference_time: datetime


class VariablePreview(BaseModel):
    global_values: dict[str, Any] = Field(default_factory=dict)
    project_values: dict[str, Any] = Field(default_factory=dict)
    template_values: dict[str, Any] = Field(default_factory=dict)
    run_values: dict[str, Any] = Field(default_factory=dict)
    value: Any


def _summary(task: TaskRecord) -> dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "labels": task.labels,
        "state": task.state,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "ended_at": task.ended_at,
    }


def _detail(task: TaskRecord, root: Path) -> dict[str, Any]:
    value = task.model_dump(mode="json")
    value["log_path"] = str(root / "logs" / task.id / "output.log")
    return value


def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    if not cursor:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(cursor + padding))
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError
        return value[0], value[1]
    except (ValueError, json.JSONDecodeError, binascii.Error):
        raise HTTPException(422, "invalid task cursor") from None


def _encode_cursor(task: TaskRecord) -> str:
    raw = json.dumps([task.created_at.isoformat(), task.id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def create_app(
    root: Path, *, settings: Settings | None = None, start_scheduler: bool = True
) -> FastAPI:
    root = root.resolve()
    initialize_root(root)
    settings = settings or load_settings(root)
    store = Store(root / "runtime" / "localflow.db")
    auth = AuthManager(root)
    config = ConfigRepository(root)
    plugins = PluginRegistry(root / "plugins")
    plugins.load()
    executor = (
        SystemdExecutor(root) if settings.execution.backend == "systemd" else SubprocessExecutor()
    )
    tasks = TaskService(
        root,
        store,
        executor,
        settings.execution.max_concurrency,
        auth.rotate_api_key,
        settings.retention,
    )
    watcher = DirectoryWatcher(root, store, config, plugins)
    time_service = TimeService(store, settings.time.privileged_helper)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        watcher_task = asyncio.create_task(watcher.run(), name="localflow-file-watcher")
        if start_scheduler:
            await tasks.start()
        yield
        watcher.stop()
        await watcher_task
        if start_scheduler:
            await tasks.stop()
        store.close()

    app = FastAPI(title="LocalFlow", version="0.1.0", lifespan=lifespan)
    app.state.root, app.state.store, app.state.tasks = root, store, tasks
    app.state.auth, app.state.config, app.state.plugins = auth, config, plugins
    app.state.watcher = watcher
    app.state.time_service = time_service

    async def require_admin(request: Request) -> str:
        authenticated = (
            auth.is_admin(request)
            if request.method in {"GET", "HEAD", "OPTIONS"}
            else auth.is_admin_mutation(request)
        )
        if authenticated:
            return "admin"
        raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator session required")

    async def require_submitter(request: Request) -> str:
        if auth.is_admin_mutation(request):
            return "admin"
        if await auth.is_signed(request):
            return "signed-client"
        raise HTTPException(status.HTTP_403_FORBIDDEN, "signed client or administrator required")

    def can_read(request: Request) -> str:
        if auth.is_admin(request):
            return "admin"
        mode = settings.server.anonymous_access
        if mode == "disabled":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "anonymous access disabled")
        return mode

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self' ws: wss:; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.post("/api/v1/auth/challenges")
    async def challenge():
        return auth.issue_nonce()

    @app.post("/api/v1/auth/local-sessions")
    async def local_session(payload: LocalLogin, request: Request, response: Response):
        token, csrf_token = auth.exchange_admin(payload.code)
        response.set_cookie(
            "localflow_session",
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=3600,
            path="/",
        )
        return {"role": "admin", "expires_in": 3600, "csrf_token": csrf_token}

    @app.get("/api/v1/auth/session")
    async def current_session(request: Request):
        csrf_token = auth.csrf_for(request)
        if not csrf_token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "administrator session required")
        return {"role": "admin", "csrf_token": csrf_token}

    @app.get("/api/v1/system/status")
    async def system_status(request: Request):
        role = can_read(request)
        return {
            "status": "ok",
            "role": role,
            "backend": settings.execution.backend,
            "anonymous_access": settings.server.anonymous_access,
            "time": time_service.status(),
        }

    @app.post("/api/v1/system/time-adjustments")
    async def adjust_time(payload: TimeAdjustment, actor: str = Depends(require_admin)):
        try:
            return await time_service.adjust(payload.reference_time, actor)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(503, str(exc)) from None

    @app.post("/api/v1/variables/resolve")
    async def resolve_variables(payload: VariablePreview, _actor: str = Depends(require_admin)):
        resolver = VariableResolver(
            [
                ("global", payload.global_values),
                ("project", payload.project_values),
                ("template", payload.template_values),
                ("run", payload.run_values),
            ]
        )
        try:
            resolution = resolver.resolution(payload.value)
        except VariableError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"value": resolution.value, "sources": resolution.sources}

    @app.post("/api/v1/tasks", status_code=202)
    async def create_task(
        payload: TaskCreate,
        actor: str = Depends(require_submitter),
        idempotency_key: Annotated[str | None, Header()] = None,
    ):
        if idempotency_key:
            previous = store.idempotency_get(actor, "/api/v1/tasks", idempotency_key)
            if previous:
                return previous
        record = tasks.submit(payload)
        result = {
            "task_id": record.id,
            "state": record.state,
            "created_at": record.created_at.isoformat(),
        }
        if idempotency_key:
            store.idempotency_put(actor, "/api/v1/tasks", idempotency_key, result)
        return result

    @app.get("/api/v1/tasks")
    async def list_tasks(
        request: Request,
        state: Annotated[list[str] | None, Query()] = None,
        label: Annotated[list[str] | None, Query()] = None,
        name: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        ended_from: datetime | None = None,
        ended_to: datetime | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        cursor: str | None = None,
    ):
        role = can_read(request)
        records = store.list_tasks(
            states=state or [],
            labels=label or [],
            name=name,
            created_from=created_from.isoformat() if created_from else None,
            created_to=created_to.isoformat() if created_to else None,
            started_from=started_from.isoformat() if started_from else None,
            started_to=started_to.isoformat() if started_to else None,
            ended_from=ended_from.isoformat() if ended_from else None,
            ended_to=ended_to.isoformat() if ended_to else None,
            limit=limit + 1,
            before=_decode_cursor(cursor),
        )
        has_more = len(records) > limit
        records = records[:limit]
        items = []
        for record in records:
            item = _detail(record, root) if role in {"admin", "readonly"} else _summary(record)
            item["newly_completed"] = bool(
                record.ended_at
                and role == "admin"
                and not store.is_acknowledged(record.id, "admin")
            )
            items.append(item)
        return {
            "items": items,
            "next_cursor": _encode_cursor(records[-1]) if has_more and records else None,
        }

    @app.get("/api/v1/tasks/{task_id}")
    async def get_task(task_id: str, request: Request):
        role = can_read(request)
        try:
            record = store.get_task(task_id)
        except KeyError:
            raise HTTPException(404, "task not found") from None
        return _detail(record, root) if role in {"admin", "readonly"} else _summary(record)

    @app.post("/api/v1/tasks/{task_id}/acknowledgements")
    async def acknowledge(task_id: str, _actor: str = Depends(require_admin)):
        try:
            store.acknowledge(task_id, "admin")
        except KeyError:
            raise HTTPException(404, "task not found") from None
        return {"acknowledged": True}

    @app.post("/api/v1/tasks/{task_id}/interrupt")
    async def interrupt(task_id: str, _actor: str = Depends(require_admin)):
        try:
            return await tasks.interrupt(
                task_id,
                settings.execution.sigint_grace_seconds,
                settings.execution.sigterm_grace_seconds,
            )
        except KeyError:
            raise HTTPException(404, "task not found") from None

    @app.get("/api/v1/tasks/{task_id}/logs")
    async def logs(task_id: str, request: Request, offset: int = 0, limit: int = 262144):
        role = can_read(request)
        if role == "summary":
            raise HTTPException(403, "logs require full read access")
        try:
            data, next_offset = tasks.read_log(task_id, offset, limit)
        except KeyError:
            raise HTTPException(404, "task not found") from None
        return {
            "offset": offset,
            "next_offset": next_offset,
            "data": base64.b64encode(data).decode(),
        }

    @app.get("/api/v1/events")
    async def events(request: Request, after: int = 0):
        can_read(request)

        async def stream():
            cursor = after
            while True:
                if await request.is_disconnected():
                    return
                found = store.events_after(cursor)
                if found:
                    for event in found:
                        cursor = event.id
                        safe_data = (
                            event.data
                            if auth.is_admin(request)
                            or settings.server.anonymous_access == "readonly"
                            else {"state": event.data.get("state")}
                        )
                        yield f"id: {event.id}\nevent: {event.kind}\ndata: {json.dumps({'task_id': event.task_id, **safe_data}, default=str)}\n\n"
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/v1/templates")
    async def templates(request: Request):
        role = can_read(request)
        if role == "summary":
            raise HTTPException(403, "templates require full read access")
        return {
            "items": plugins.describe(),
            "diagnostics": plugins.diagnostics if role == "admin" else {},
        }

    @app.post("/api/v1/templates/{name}/runs", status_code=202)
    async def run_template(name: str, values: dict[str, Any], _actor: str = Depends(require_admin)):
        try:
            drafts = plugins.expand(name, values, {"root": str(root)})
        except KeyError:
            raise HTTPException(404, "template not found") from None
        records = [tasks.submit(draft) for draft in drafts]
        return {"task_ids": [item.id for item in records], "count": len(records)}

    @app.post("/api/v1/templates/{name}/discover")
    async def discover_template(
        name: str, values: dict[str, Any], _actor: str = Depends(require_admin)
    ):
        try:
            options = await plugins.discover(name, values)
        except KeyError:
            raise HTTPException(404, "template not found") from None
        except TimeoutError:
            raise HTTPException(504, "plugin discovery timed out") from None
        except Exception as exc:
            raise HTTPException(422, f"plugin discovery failed: {exc}") from None
        return {"items": options}

    @app.post("/api/v1/batches", status_code=202)
    async def create_batch(
        payload: BatchCreate,
        actor: str = Depends(require_submitter),
        idempotency_key: Annotated[str | None, Header()] = None,
    ):
        route = "/api/v1/batches"
        if idempotency_key:
            previous = store.idempotency_get(actor, route, idempotency_key)
            if previous:
                return previous
        try:
            expanded = plugins.expand(payload.template, payload.values, {"root": str(root)})
        except KeyError:
            raise HTTPException(404, "template not found") from None
        drafts = []
        for draft in expanded:
            data = draft.model_dump()
            data.update(payload.common)
            drafts.append(TaskCreate.model_validate(data))
        batch_id, records = tasks.submit_batch(payload.template, payload.values, drafts)
        result = {
            "batch_id": batch_id,
            "task_ids": [record.id for record in records],
            "count": len(records),
        }
        if idempotency_key:
            store.idempotency_put(actor, route, idempotency_key, result)
        return result

    @app.get("/api/v1/batches/{batch_id}")
    async def get_batch(batch_id: str, request: Request):
        can_read(request)
        try:
            return store.get_batch(batch_id)
        except KeyError:
            raise HTTPException(404, "batch not found") from None

    @app.get("/api/v1/config/files")
    async def config_files(_actor: str = Depends(require_admin)):
        return {"items": config.list()}

    @app.get("/api/v1/config/files/{path:path}")
    async def config_read(path: str, _actor: str = Depends(require_admin)):
        try:
            return config.read(path).__dict__
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from None

    @app.put("/api/v1/config/files/{path:path}")
    async def config_write(
        path: str,
        payload: ConfigWrite,
        _actor: str = Depends(require_admin),
        if_match: Annotated[str | None, Header()] = None,
    ):
        try:
            return config.write(path, payload.content, if_match).__dict__
        except ConfigConflict as exc:
            raise HTTPException(412, {"current_version": str(exc)}) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.websocket("/api/v1/tasks/{task_id}/terminal")
    async def terminal(websocket: WebSocket, task_id: str):
        is_admin = auth.is_websocket_admin(websocket)
        if settings.server.anonymous_access == "disabled" and not is_admin:
            await websocket.close(code=4403)
            return
        if settings.server.anonymous_access == "summary" and not is_admin:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        offset = 0
        try:
            while True:
                data, offset = tasks.read_log(task_id, offset, 65536)
                if data:
                    await websocket.send_json(
                        {
                            "type": "output",
                            "data": base64.b64encode(data).decode(),
                            "offset": offset,
                        }
                    )
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), 0.5)
                    message_type = message.get("type")
                    if message_type in {"input", "resize"} and not is_admin:
                        await websocket.send_json(
                            {"type": "error", "message": "read-only terminal"}
                        )
                    elif message_type == "input":
                        data = base64.b64decode(str(message.get("data", "")), validate=True)
                        if len(data) > 65536 or not await tasks.write_terminal(task_id, data):
                            await websocket.send_json(
                                {"type": "error", "message": "terminal input rejected"}
                            )
                    elif message_type == "resize":
                        accepted = await tasks.resize_terminal(
                            task_id,
                            int(message.get("rows", 0)),
                            int(message.get("cols", 0)),
                        )
                        if not accepted:
                            await websocket.send_json(
                                {"type": "error", "message": "terminal resize rejected"}
                            )
                except (binascii.Error, ValueError, TypeError):
                    await websocket.send_json(
                        {"type": "error", "message": "invalid terminal message"}
                    )
                except TimeoutError:
                    pass
        except (WebSocketDisconnect, KeyError):
            return

    dist_candidates = []
    configured_dist = os.environ.get("LOCALFLOW_WEB_DIST")
    if configured_dist:
        configured_path = Path(configured_dist)
        if not configured_path.is_dir():
            raise RuntimeError(f"LOCALFLOW_WEB_DIST is not a directory: {configured_path}")
        dist_candidates.append(configured_path)
    dist_candidates.extend(
        [
            Path(getattr(sys, "_MEIPASS", "")) / "frontend" / "dist",
            Path("/opt/localflow/frontend/dist"),
            Path(__file__).resolve().parents[2] / "frontend" / "dist",
        ]
    )
    dist = next((candidate.resolve() for candidate in dist_candidates if candidate.is_dir()), None)
    if dist is not None:
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            candidate = dist / path
            return FileResponse(candidate if candidate.is_file() else dist / "index.html")

    return app
