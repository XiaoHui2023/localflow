from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
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
from .config_diagnostics import ConfigDiagnosis, diagnose_config
from .config_repository import ConfigConflict, ConfigRepository
from .executor import SubprocessExecutor, SystemdExecutor, systemd_user_manager_available
from .models import BatchCreate, RunCreate, TaskCreate, TaskDraft, TaskRecord
from .plugins import PluginRegistry
from .service import TaskService
from .settings import Settings, initialize_root, load_settings
from .storage import Store
from .time_service import TimeService
from .variables import VariableError, VariableResolver
from .watcher import DirectoryWatcher
from .workspace_repository import WorkspaceConflict, WorkspaceRepository

logger = logging.getLogger(__name__)


class WebAdminLogin(BaseModel):
    key: str


class ConfigWrite(BaseModel):
    content: str


class ConfigMove(BaseModel):
    target: str
    version: str


class ConfigRun(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class ConfigCreate(BaseModel):
    path: str
    plugin: str


class WorkspaceCreateDirectory(BaseModel):
    path: str


class WorkspaceTransfer(BaseModel):
    source: str
    target: str


class TimeAdjustment(BaseModel):
    reference_time: datetime


class TerminalInput(BaseModel):
    data: str
    encoding: Literal["utf-8", "base64"] = "utf-8"


class TerminalControl(BaseModel):
    key: Literal["ctrl_c", "ctrl_d", "enter", "escape", "tab"]


class TerminalResize(BaseModel):
    rows: int = Field(ge=2, le=1000)
    cols: int = Field(ge=2, le=1000)


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
        "status": task.status.model_dump(),
        "created_at": task.created_at,
        "started_at": task.started_at,
        "ended_at": task.ended_at,
    }


def _detail(task: TaskRecord, root: Path) -> dict[str, Any]:
    value = task.model_dump(mode="json")
    value["log_path"] = str(root / "logs" / task.id / "output.log")
    return value


def _plan(plugin_name: str, drafts: list[TaskCreate]) -> dict[str, Any]:
    items = []
    for sequence, draft in enumerate(drafts):
        deferred = (
            {name: value.model_dump() for name, value in draft.deferred_values.items()}
            if isinstance(draft, TaskDraft)
            else {}
        )
        items.append(
            {
                "sequence": sequence,
                "name": draft.name,
                "working_directory": draft.working_directory,
                "command": draft.command,
                "labels": draft.labels,
                "mutex_keys": draft.mutex_keys,
                "custom": draft.custom,
                "deferred_values": deferred,
            }
        )
    return {
        "plugin": plugin_name,
        "count": len(items),
        "immutable_after_submit": True,
        "items": items,
    }


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


def _inline_script_csp_hashes(index: Path) -> tuple[str, ...]:
    """Return CSP hashes for inline scripts emitted into the final SPA entry."""
    if not index.is_file():
        return ()
    html = index.read_bytes().decode("utf-8")
    script_elements = re.findall(
        r"<script\b([^>]*)>(.*?)</script\s*>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    scripts = (
        body
        for attributes, body in script_elements
        if not re.search(r"(?:^|\s)src\s*=", attributes, flags=re.IGNORECASE)
    )
    return tuple(
        "'sha256-"
        + base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
        + "'"
        for script in scripts
        if script
    )


def _initial_event_cursor(store: Store, after: int | None, last_event_id: str | None) -> int:
    if after is not None:
        return after
    if last_event_id:
        try:
            return max(0, int(last_event_id))
        except ValueError:
            pass
    return store.latest_event_id()


def create_app(
    root: Path, *, settings: Settings | None = None, start_scheduler: bool = True
) -> FastAPI:
    root = root.resolve()
    initialize_root(root)
    settings = settings or load_settings(root)
    store = Store(
        root / "runtime" / "localflow.db",
        database_max_bytes=settings.logging.database_mb * 1024 * 1024,
        wal_max_bytes=settings.logging.wal_mb * 1024 * 1024,
    )
    auth = AuthManager(root)
    plugins = PluginRegistry(root / "plugins")
    plugins.load()
    config = ConfigRepository(root, lambda document: diagnose_config(document, plugins))
    workspace = WorkspaceRepository(root, config)
    use_systemd = settings.execution.backend == "systemd"
    if settings.execution.backend == "auto":
        use_systemd, reason = systemd_user_manager_available()
        if not use_systemd:
            logger.warning("systemd unavailable; using subprocess backend reason=%s", reason)
    executor = (
        SystemdExecutor(
            root,
            task_log_max_bytes=settings.logging.task_file_mb * 1024 * 1024,
            keep_free_bytes=settings.logging.keep_free_mb * 1024 * 1024,
        )
        if use_systemd
        else SubprocessExecutor(
            task_log_max_bytes=settings.logging.task_file_mb * 1024 * 1024,
            keep_free_bytes=settings.logging.keep_free_mb * 1024 * 1024,
        )
    )
    tasks = TaskService(
        root,
        store,
        executor,
        settings.execution.max_concurrency,
        auth.rotate_api_key,
        settings.retention,
        settings.logging,
        plugins.evaluate_result,
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
            await tasks.shutdown_all()
            await tasks.stop()
        store.close()

    app = FastAPI(
        title="LocalFlow",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    inline_script_hashes: tuple[str, ...] = ()

    @app.middleware("http")
    async def prevent_stale_operator_pages(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
    app.state.root, app.state.store, app.state.tasks = root, store, tasks
    app.state.auth, app.state.config, app.state.plugins = auth, config, plugins
    app.state.watcher = watcher
    app.state.time_service = time_service

    def set_admin_cookie(request: Request, response: Response, token: str) -> None:
        response.set_cookie(
            "localflow_session",
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=34_560_000,
            path="/",
        )

    async def require_admin(request: Request) -> str:
        authenticated = auth.is_admin(request) if request.method in {
            "GET", "HEAD", "OPTIONS"
        } else auth.is_admin_mutation(request)
        if authenticated:
            return "admin"
        raise HTTPException(status.HTTP_403_FORBIDDEN, "administrator session required")

    async def require_submitter(request: Request) -> str:
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            if auth.is_admin(request):
                return "admin"
        elif auth.is_admin_mutation(request):
            return "admin"
        if await auth.is_signed(request):
            return "signed-client"
        raise HTTPException(status.HTTP_403_FORBIDDEN, "signed client or administrator required")

    async def can_read(request: Request) -> str:
        if auth.is_admin(request):
            return "admin"
        signed_attempt = any(
            request.headers.get(name)
            for name in (
                "x-localflow-nonce",
                "x-localflow-created",
                "x-localflow-generation",
                "x-localflow-signature",
            )
        )
        if await auth.is_signed(request):
            return "signed-client"
        if signed_attempt:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid signed client request")
        mode = settings.server.anonymous_access
        if mode == "disabled":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "anonymous access disabled")
        return mode

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        script_policy = "script-src 'self'"
        if inline_script_hashes:
            script_policy += " " + " ".join(inline_script_hashes)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; " + script_policy + "; connect-src 'self' ws: wss:; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.post("/api/v1/auth/challenges")
    async def challenge():
        return auth.issue_nonce()

    @app.post("/api/v1/auth/local-sessions")
    async def local_session(payload: WebAdminLogin, request: Request, response: Response):
        token, csrf_token = auth.exchange_admin(payload.key)
        set_admin_cookie(request, response, token)
        return {"role": "admin", "persistent": True, "csrf_token": csrf_token}

    @app.get("/api/v1/auth/session")
    async def current_session(request: Request, response: Response):
        csrf_token = auth.csrf_for(request)
        if not csrf_token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "administrator session required")
        token = auth.cookie_token(request)
        if token:
            set_admin_cookie(request, response, token)
        return {"role": "admin", "persistent": True, "csrf_token": csrf_token}

    @app.get("/api/v1/openapi", include_in_schema=False)
    async def protected_openapi(_actor: str = Depends(require_admin)):
        return app.openapi()

    @app.get("/api/v1/system/status")
    async def system_status(request: Request):
        role = await can_read(request)
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
    async def resolve_variables(payload: VariablePreview, _actor: str = Depends(require_submitter)):
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
        role = await can_read(request)
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
            item = (
                _detail(record, root)
                if role in {"admin", "readonly", "signed-client"}
                else _summary(record)
            )
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
        role = await can_read(request)
        try:
            record = store.get_task(task_id)
        except KeyError:
            raise HTTPException(404, "task not found") from None
        return (
            _detail(record, root)
            if role in {"admin", "readonly", "signed-client"}
            else _summary(record)
        )

    @app.post("/api/v1/tasks/{task_id}/acknowledgements")
    async def acknowledge(task_id: str, _actor: str = Depends(require_submitter)):
        try:
            store.acknowledge(task_id, "admin")
        except KeyError:
            raise HTTPException(404, "task not found") from None
        return {"acknowledged": True}

    @app.post("/api/v1/tasks/{task_id}/interrupt")
    async def interrupt(task_id: str, _actor: str = Depends(require_submitter)):
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
        role = await can_read(request)
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

    @app.post("/api/v1/tasks/{task_id}/terminal/input")
    async def terminal_input(
        task_id: str, payload: TerminalInput, _actor: str = Depends(require_submitter)
    ):
        try:
            data = (
                base64.b64decode(payload.data, validate=True)
                if payload.encoding == "base64"
                else payload.data.encode()
            )
        except (ValueError, binascii.Error):
            raise HTTPException(422, "invalid terminal input") from None
        if not data or len(data) > 65536:
            raise HTTPException(422, "terminal input must be 1..65536 bytes")
        try:
            accepted = await tasks.write_terminal(task_id, data)
        except KeyError:
            raise HTTPException(404, "task not found") from None
        if not accepted:
            raise HTTPException(409, "task terminal is not writable")
        return {"accepted": len(data)}

    @app.post("/api/v1/tasks/{task_id}/terminal/controls")
    async def terminal_control(
        task_id: str, payload: TerminalControl, _actor: str = Depends(require_submitter)
    ):
        controls = {
            "ctrl_c": b"\x03",
            "ctrl_d": b"\x04",
            "enter": b"\r",
            "escape": b"\x1b",
            "tab": b"\t",
        }
        try:
            accepted = await tasks.write_terminal(task_id, controls[payload.key])
        except KeyError:
            raise HTTPException(404, "task not found") from None
        if not accepted:
            raise HTTPException(409, "task terminal is not writable")
        return {"accepted": payload.key}

    @app.post("/api/v1/tasks/{task_id}/terminal/resize")
    async def terminal_resize(
        task_id: str, payload: TerminalResize, _actor: str = Depends(require_submitter)
    ):
        try:
            accepted = await tasks.resize_terminal(task_id, payload.rows, payload.cols)
        except KeyError:
            raise HTTPException(404, "task not found") from None
        if not accepted:
            raise HTTPException(409, "task terminal is not resizable")
        return {"accepted": True, "rows": payload.rows, "cols": payload.cols}

    @app.get("/api/v1/events")
    async def events(
        request: Request,
        after: Annotated[int | None, Query(ge=0)] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ):
        await can_read(request)

        async def stream():
            cursor = _initial_event_cursor(store, after, last_event_id)
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
        role = await can_read(request)
        if role == "summary":
            raise HTTPException(403, "templates require full read access")
        return {
            "items": plugins.describe(),
            "diagnostics": plugins.diagnostics if role == "admin" else {},
        }

    @app.get("/api/v1/plugins")
    async def loaded_plugins(_actor: str = Depends(require_submitter)):
        return {"items": plugins.describe(), "diagnostics": plugins.diagnostics}

    @app.get("/api/v1/plugins/{name}")
    async def loaded_plugin(name: str, _actor: str = Depends(require_submitter)):
        item = next((item for item in plugins.describe() if item["name"] == name), None)
        if item is None:
            raise HTTPException(404, "plugin not found")
        return item

    @app.post("/api/v1/templates/{name}/runs", status_code=202)
    async def run_template(
        name: str, values: dict[str, Any], _actor: str = Depends(require_submitter)
    ):
        try:
            drafts = plugins.expand(name, values, {"root": str(root)})
        except KeyError:
            raise HTTPException(404, "template not found") from None
        records = [tasks.submit(draft) for draft in drafts]
        return {"task_ids": [item.id for item in records], "count": len(records)}

    @app.post("/api/v1/templates/{name}/discover")
    async def discover_template(
        name: str, values: dict[str, Any], _actor: str = Depends(require_submitter)
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
        try:
            expanded = plugins.expand(payload.template, payload.values, {"root": str(root)})
        except KeyError:
            raise HTTPException(404, "template not found") from None
        drafts = [draft.model_copy(update=payload.common) for draft in expanded]
        batch_id, records = tasks.submit_batch(
            payload.template,
            payload.values,
            drafts,
            (actor, route, idempotency_key) if idempotency_key else None,
        )
        result = {
            "batch_id": batch_id,
            "task_ids": [record.id for record in records],
            "count": len(records),
        }
        return result

    @app.post("/api/v1/runs/plan")
    async def plan_run(payload: RunCreate, _actor: str = Depends(require_submitter)):
        plugin_name = payload.configuration.get("plugin")
        if isinstance(plugin_name, str) and plugin_name not in plugins.plugins:
            raise HTTPException(404, "plugin not found")
        diagnosis = diagnose_config(payload.configuration, plugins)
        if not diagnosis.runnable:
            raise HTTPException(
                422,
                {
                    "message": "configuration is not runnable",
                    "errors": diagnosis.errors,
                    "warnings": diagnosis.warnings,
                },
            )
        try:
            drafts = plugins.expand_config(
                payload.configuration, payload.inputs, {"root": str(root)}
            )
        except KeyError:
            raise HTTPException(404, "plugin not found") from None
        except Exception as exc:
            raise HTTPException(422, f"configuration expansion failed: {exc}") from None
        return _plan(str(plugin_name), drafts)

    @app.post("/api/v1/runs", status_code=202)
    async def create_run(
        payload: RunCreate,
        actor: str = Depends(require_submitter),
        idempotency_key: Annotated[str | None, Header()] = None,
    ):
        """Validate an inline configuration through its plugin and atomically queue its tasks."""

        route = "/api/v1/runs"
        plugin_name = payload.configuration.get("plugin")
        if isinstance(plugin_name, str) and plugin_name not in plugins.plugins:
            raise HTTPException(404, "plugin not found")
        diagnosis = diagnose_config(payload.configuration, plugins)
        if not diagnosis.runnable:
            raise HTTPException(
                422,
                {
                    "message": "configuration is not runnable",
                    "errors": diagnosis.errors,
                    "warnings": diagnosis.warnings,
                },
            )
        try:
            drafts = plugins.expand_config(
                payload.configuration,
                payload.inputs,
                {"root": str(root)},
            )
        except KeyError:
            raise HTTPException(404, "plugin not found") from None
        except Exception as exc:
            raise HTTPException(422, f"configuration expansion failed: {exc}") from None
        batch_id, records = tasks.submit_batch(
            str(plugin_name),
            {"configuration": payload.configuration, "inputs": payload.inputs},
            drafts,
            (actor, route, idempotency_key) if idempotency_key else None,
        )
        result = {
            "batch_id": batch_id,
            "task_ids": [record.id for record in records],
            "count": len(records),
        }
        return result

    @app.get("/api/v1/batches/{batch_id}")
    async def get_batch(batch_id: str, request: Request):
        await can_read(request)
        try:
            return store.get_batch(batch_id)
        except KeyError:
            raise HTTPException(404, "batch not found") from None

    @app.get("/api/v1/config/files")
    async def config_files(_actor: str = Depends(require_submitter)):
        items = config.list()
        diagnostics: dict[str, dict[str, Any]] = {}
        for path in items:
            try:
                diagnosis = diagnose_config(config.parse(path), plugins)
            except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
                diagnosis = ConfigDiagnosis(
                    kind="generic",
                    valid=False,
                    runnable=False,
                    errors=[f"syntax or import error: {error}"],
                )
            diagnostics[path] = diagnosis.model_dump()
        return {"items": items, "diagnostics": diagnostics}

    @app.get("/api/v1/workspace")
    async def workspace_entries(_actor: str = Depends(require_submitter)):
        entries = workspace.entries()
        diagnostics: dict[str, dict[str, Any]] = {}
        for entry in entries:
            path = str(entry["path"])
            if entry["kind"] != "file" or not path.startswith("config/"):
                continue
            relative = path.split("/", 1)[1]
            try:
                diagnosis = diagnose_config(config.parse(relative), plugins)
            except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
                diagnosis = ConfigDiagnosis(kind="generic", valid=False, runnable=False, errors=[f"syntax or import error: {error}"])
            diagnostics[path] = diagnosis.model_dump()
        return {"items": entries, "diagnostics": diagnostics}

    @app.get("/api/v1/workspace/files/{path:path}")
    async def workspace_read(path: str, _actor: str = Depends(require_submitter)):
        try:
            item = workspace.read(path)
            result: dict[str, Any] = item.__dict__.copy()
            if path.startswith("config/"):
                relative = path.split("/", 1)[1]
                try:
                    document = config.parse(relative)
                    diagnosis = diagnose_config(document, plugins)
                except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
                    document = None
                    diagnosis = ConfigDiagnosis(kind="generic", valid=False, runnable=False, errors=[f"syntax or import error: {error}"])
                result.update(document=document, plugin=document.get("plugin") if isinstance(document, dict) else None, diagnosis=diagnosis.model_dump())
            return result
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from None

    @app.put("/api/v1/workspace/files/{path:path}")
    async def workspace_write(path: str, payload: ConfigWrite, _actor: str = Depends(require_submitter), if_match: Annotated[str | None, Header()] = None):
        try:
            return workspace.write(path, payload.content, if_match).__dict__
        except WorkspaceConflict as exc:
            raise HTTPException(412, {"current_version": str(exc)}) from None
        except (SyntaxError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/v1/workspace/directories", status_code=201)
    async def workspace_create_directory(payload: WorkspaceCreateDirectory, _actor: str = Depends(require_submitter)):
        try:
            workspace.create_directory(payload.path)
            return {"path": payload.path}
        except FileExistsError:
            raise HTTPException(409, "workspace entry already exists") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/v1/workspace/moves")
    async def workspace_move(payload: WorkspaceTransfer, _actor: str = Depends(require_submitter)):
        try:
            workspace.move(payload.source, payload.target)
            return {"path": payload.target}
        except FileExistsError:
            raise HTTPException(409, "workspace target already exists") from None
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/v1/workspace/copies", status_code=201)
    async def workspace_copy(payload: WorkspaceTransfer, _actor: str = Depends(require_submitter)):
        try:
            workspace.copy(payload.source, payload.target)
            return {"path": payload.target}
        except FileExistsError:
            raise HTTPException(409, "workspace target already exists") from None
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None

    @app.delete("/api/v1/workspace/entries/{path:path}", status_code=204)
    async def workspace_delete(path: str, _actor: str = Depends(require_submitter)):
        try:
            workspace.delete(path)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        return Response(status_code=204)

    @app.post("/api/v1/config/files", status_code=201)
    async def config_create(
        payload: ConfigCreate, _actor: str = Depends(require_submitter)
    ):
        try:
            example = plugins.example(payload.plugin)
            example = {**example, "plugin": payload.plugin}
            content = yaml.safe_dump(example, allow_unicode=True, sort_keys=False)
            return config.write(payload.path, content, None).__dict__
        except KeyError:
            raise HTTPException(404, "configuration plugin is not loaded") from None
        except (ConfigConflict, FileExistsError):
            raise HTTPException(409, "configuration already exists") from None
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/v1/config/files/{path:path}")
    async def config_read(path: str, _actor: str = Depends(require_submitter)):
        try:
            item = config.read(path)
            try:
                document = config.parse(path)
                diagnosis = diagnose_config(document, plugins)
            except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
                document = None
                diagnosis = ConfigDiagnosis(
                    kind="generic",
                    valid=False,
                    runnable=False,
                    errors=[f"syntax or import error: {error}"],
                )
            plugin_name = document.get("plugin") if isinstance(document, dict) else None
            return {
                **item.__dict__,
                "document": document,
                "plugin": plugin_name,
                "plugin_loaded": plugin_name in plugins.plugins if plugin_name else False,
                "diagnosis": diagnosis.model_dump(),
            }
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from None

    @app.put("/api/v1/config/files/{path:path}")
    async def config_write(
        path: str,
        payload: ConfigWrite,
        _actor: str = Depends(require_submitter),
        if_match: Annotated[str | None, Header()] = None,
    ):
        try:
            return config.write(path, payload.content, if_match).__dict__
        except ConfigConflict as exc:
            raise HTTPException(412, {"current_version": str(exc)}) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/v1/config/files/{path:path}/move")
    async def config_move(
        path: str, payload: ConfigMove, _actor: str = Depends(require_submitter)
    ):
        try:
            return config.move(path, payload.target, payload.version).__dict__
        except ConfigConflict as exc:
            raise HTTPException(412, {"current_version": str(exc)}) from None
        except FileExistsError:
            raise HTTPException(409, "target configuration already exists") from None
        except (TypeError, ValueError, FileNotFoundError, yaml.YAMLError) as exc:
            raise HTTPException(422, str(exc)) from None

    @app.delete("/api/v1/config/files/{path:path}", status_code=204)
    async def config_delete(
        path: str,
        _actor: str = Depends(require_submitter),
        if_match: Annotated[str | None, Header()] = None,
    ):
        if not if_match:
            raise HTTPException(428, "If-Match is required")
        try:
            config.delete(path, if_match)
        except ConfigConflict as exc:
            raise HTTPException(412, {"current_version": str(exc)}) from None
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from None
        return Response(status_code=204)

    @app.post("/api/v1/config/files/{path:path}/plan")
    async def config_plan(
        path: str, payload: ConfigRun, _actor: str = Depends(require_submitter)
    ):
        try:
            document = config.parse(path)
            diagnosis = diagnose_config(document, plugins)
            if not diagnosis.runnable:
                raise ValueError("; ".join(diagnosis.errors) or "configuration is not runnable")
            drafts = plugins.expand_config(
                document,
                payload.inputs,
                {"root": str(root), "config_path": path},
            )
        except KeyError:
            raise HTTPException(404, "configuration plugin is not loaded") from None
        except (TypeError, ValueError, FileNotFoundError, yaml.YAMLError) as exc:
            raise HTTPException(422, str(exc)) from None
        return _plan(str(document["plugin"]), drafts)

    @app.post("/api/v1/config/files/{path:path}/runs", status_code=202)
    async def config_run(
        path: str,
        payload: ConfigRun,
        actor: str = Depends(require_submitter),
        idempotency_key: Annotated[str | None, Header()] = None,
    ):
        try:
            document = config.parse(path)
            diagnosis = diagnose_config(document, plugins)
            if not diagnosis.runnable:
                raise ValueError("; ".join(diagnosis.errors) or "configuration is not runnable")
            drafts = plugins.expand_config(
                document,
                payload.inputs,
                {"root": str(root), "config_path": path},
            )
        except KeyError:
            raise HTTPException(404, "configuration plugin is not loaded") from None
        except (TypeError, ValueError, FileNotFoundError, yaml.YAMLError) as exc:
            raise HTTPException(422, str(exc)) from None
        route = f"/api/v1/config/files/{path}/runs"
        batch_id, records = tasks.submit_batch(
            str(document["plugin"]),
            {"configuration_path": path, "inputs": payload.inputs},
            drafts,
            (actor, route, idempotency_key) if idempotency_key else None,
        )
        result = {
            "batch_id": batch_id,
            "task_ids": [item.id for item in records],
            "count": len(records),
        }
        return result

    @app.post("/api/v1/config/files/{path:path}/discover")
    async def config_discover(
        path: str, payload: ConfigRun, _actor: str = Depends(require_submitter)
    ):
        try:
            document = config.parse(path)
            diagnosis = diagnose_config(document, plugins)
            if not diagnosis.runnable:
                raise ValueError("; ".join(diagnosis.errors) or "configuration is not runnable")
            items = await plugins.discover_config(
                document,
                payload.inputs,
                {"root": str(root), "config_path": path},
            )
        except KeyError:
            raise HTTPException(404, "configuration plugin is not loaded") from None
        except TimeoutError:
            raise HTTPException(504, "plugin discovery timed out") from None
        except (TypeError, ValueError, FileNotFoundError, OSError, yaml.YAMLError) as exc:
            raise HTTPException(422, f"plugin discovery failed: {exc}") from None
        return {"items": items}

    @app.post("/api/v1/config/files/{path:path}/inspection")
    async def config_inspection(
        path: str, payload: ConfigRun, _actor: str = Depends(require_submitter)
    ):
        try:
            document = config.parse(path)
            diagnosis = diagnose_config(document, plugins)
            if not diagnosis.runnable:
                raise ValueError("; ".join(diagnosis.errors) or "configuration is not runnable")
            items = await plugins.inspect_config(
                document,
                payload.inputs,
                {"root": str(root), "config_path": path},
            )
        except KeyError:
            raise HTTPException(404, "configuration plugin is not loaded") from None
        except TimeoutError:
            raise HTTPException(504, "plugin inspection timed out") from None
        except (TypeError, ValueError, FileNotFoundError, OSError, yaml.YAMLError) as exc:
            raise HTTPException(422, f"plugin inspection failed: {exc}") from None
        return {"items": items}

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
        awaiting_ack = False
        try:
            while True:
                data = b""
                if not awaiting_ack:
                    data, offset = tasks.read_log(task_id, offset, 65536)
                if data:
                    await websocket.send_json(
                        {
                            "type": "output",
                            "data": base64.b64encode(data).decode(),
                            "offset": offset,
                        }
                    )
                    awaiting_ack = True
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), 0.1)
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
                    elif message_type == "ack":
                        awaiting_ack = False
                except (binascii.Error, ValueError, TypeError):
                    await websocket.send_json(
                        {"type": "error", "message": "invalid terminal message"}
                    )
                except TimeoutError:
                    pass
        except (WebSocketDisconnect, KeyError):
            return

    @app.get("/docs", include_in_schema=False)
    @app.get("/redoc", include_in_schema=False)
    @app.get("/openapi.json", include_in_schema=False)
    async def disabled_public_documentation():
        raise HTTPException(404, "public API documentation is disabled")

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
        inline_script_hashes = _inline_script_csp_hashes(dist / "index.html")
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/api/v1/system/ui-revision", include_in_schema=False)
        async def ui_revision():
            index = dist / "index.html"
            stat = index.stat()
            return {"revision": f"{stat.st_mtime_ns:x}-{stat.st_size:x}"}

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "API route not found")
            candidate = (dist / path).resolve()
            try:
                candidate.relative_to(dist)
            except ValueError:
                raise HTTPException(404, "file not found") from None
            served = candidate if candidate.is_file() else dist / "index.html"
            headers = {"Cache-Control": "no-store"} if served.name == "index.html" else None
            return FileResponse(served, headers=headers)

    return app
