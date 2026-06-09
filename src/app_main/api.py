from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

import blueprints as blueprint_store
import history_hook  # noqa: F401 — 注册运行结束快照
import run_history as run_history_store
from automation_catalog import automation_descriptors
from automation.script.registry import (
    finished_script_descriptors,
    get_script,
    running_script_descriptors,
    script_descriptors,
)
from automation.script.runner import cancel_script


@dataclass
class TaskState:
    running: bool = False
    progress: int = 0
    message: str = ""
    result: dict[str, Any] | None = None


@dataclass
class AppState:
    config: dict[str, Any] = field(
        default_factory=lambda: {
            "mode": "idle",
            "listen_host": "0.0.0.0",
        }
    )
    task: TaskState = field(default_factory=TaskState)
    lock: threading.Lock = field(default_factory=threading.Lock)


_STATE = AppState()


def get_state() -> AppState:
    return _STATE


def _read_json_body(handler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("请求体须为 JSON 对象")
    return data


def _send_json(handler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _api_status() -> dict[str, Any]:
    state = get_state()
    with state.lock:
        task = state.task
        return {
            "ok": True,
            "running": task.running,
            "progress": task.progress,
            "message": task.message,
        }


def _api_config() -> dict[str, Any]:
    state = get_state()
    with state.lock:
        return {"ok": True, "config": dict(state.config)}


def _api_run(body: dict[str, Any]) -> dict[str, Any]:
    state = get_state()
    with state.lock:
        if state.task.running:
            return {"ok": False, "error": "已有任务在运行"}
        state.task = TaskState(
            running=True,
            progress=0,
            message="任务已启动（占位）",
            result=None,
        )
        if body:
            state.config.update({k: v for k, v in body.items() if k != "password"})
    return {"ok": True, "started": True}


def _api_progress() -> dict[str, Any]:
    state = get_state()
    with state.lock:
        task = state.task
        return {
            "ok": True,
            "running": task.running,
            "progress": task.progress,
            "message": task.message,
        }


def _api_automations() -> dict[str, Any]:
    return {"ok": True, "automations": automation_descriptors()}


def _api_scripts() -> dict[str, Any]:
    return {
        "ok": True,
        "running": running_script_descriptors(),
        "finished": finished_script_descriptors(),
        "scripts": script_descriptors(),
    }


def _api_script(instance_id: str) -> dict[str, Any]:
    script = get_script(instance_id)
    if script is None:
        return {"ok": False, "error": "未找到 Script 实例"}
    return {"ok": True, "script": script.describe()}


def _api_script_terminal(instance_id: str) -> dict[str, Any]:
    script = get_script(instance_id)
    if script is None:
        return {"ok": False, "error": "未找到 Script 实例"}
    return {
        "ok": True,
        "terminal": script.terminal_text(),
        "terminal_log_path": str(script.terminal_log_path) if script.terminal_log_path else None,
    }


def _apply_script_variables(script: Any, body: dict[str, Any]) -> dict[str, Any] | None:
    batch_params = body.get("batch_params")
    if batch_params is not None:
        if not isinstance(batch_params, dict):
            return {"ok": False, "error": "batch_params 须为 JSON 对象"}
        apply_batch = getattr(script, "apply_batch_params", None)
        if apply_batch is None:
            return {"ok": False, "error": "该 Script 不支持 batch_params"}
        apply_batch(batch_params)
        return None
    variables = body.get("variables")
    if variables is None:
        return None
    if not isinstance(variables, dict):
        return {"ok": False, "error": "variables 须为 JSON 对象"}
    script.apply_user_variables(variables)
    return None


def _api_script_variables(instance_id: str, body: dict[str, Any]) -> dict[str, Any]:
    script = get_script(instance_id)
    if script is None:
        return {"ok": False, "error": "未找到 Script 实例"}
    if script.status.value == "running":
        return {"ok": False, "error": "运行中不可修改参数"}
    err = _apply_script_variables(script, body)
    if err is not None:
        return err
    return {"ok": True, "script": script.describe()}


def _api_script_cancel(instance_id: str, body: dict[str, Any]) -> dict[str, Any]:
    script = get_script(instance_id)
    if script is None:
        return {"ok": False, "error": "未找到 Script 实例"}
    force = bool(body.get("force"))
    result = cancel_script(script, force=force)
    if not result.get("ok"):
        return result
    return {"ok": True, **result, "script": script.describe()}


def _api_script_start(instance_id: str, body: dict[str, Any]) -> dict[str, Any]:
    script = get_script(instance_id)
    if script is None:
        return {"ok": False, "error": "未找到 Script 实例"}
    if script.status.value == "running":
        return {"ok": False, "error": "该 Script 已在运行"}
    err = _apply_script_variables(script, body)
    if err is not None:
        return err
    log_path = body.get("terminal_log_path")
    started = script.start(terminal_log_path=log_path if log_path else None)
    if not started:
        return {"ok": False, "error": "该 Script 已在运行"}
    return {"ok": True, "started": True, "id": instance_id, "script": script.describe()}


def _blueprint_run_body(record: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if record.get("is_batch"):
        body["batch_params"] = record.get("batch_params") or {}
    else:
        body["variables"] = record.get("variables") or {}
    return body


def _api_blueprints(script_id: str | None = None) -> dict[str, Any]:
    return {"ok": True, "blueprints": blueprint_store.list_blueprints(script_id=script_id)}


def _api_blueprint_get(blueprint_id: str) -> dict[str, Any]:
    record = blueprint_store.get_blueprint(blueprint_id)
    if record is None:
        return {"ok": False, "error": "未找到蓝图"}
    return {"ok": True, "blueprint": record}


def _api_blueprint_save(body: dict[str, Any]) -> dict[str, Any]:
    record = blueprint_store.save_blueprint(body)
    return {"ok": True, "blueprint": record}


def _api_blueprint_delete(blueprint_id: str) -> dict[str, Any]:
    if not blueprint_store.delete_blueprint(blueprint_id):
        return {"ok": False, "error": "未找到蓝图"}
    return {"ok": True, "deleted": True}


def _api_run_history(script_id: str | None = None) -> dict[str, Any]:
    return {"ok": True, "history": run_history_store.list_run_history(script_id=script_id)}


def _api_run_history_get(history_id: str) -> dict[str, Any]:
    record = run_history_store.get_run_history(history_id)
    if record is None:
        return {"ok": False, "error": "未找到历史记录"}
    return {"ok": True, "record": record}


def _api_blueprint_run(blueprint_id: str) -> dict[str, Any]:
    record = blueprint_store.get_blueprint(blueprint_id)
    if record is None:
        return {"ok": False, "error": "未找到蓝图"}
    script_id = str(record.get("script_id", ""))
    return _api_script_start(script_id, _blueprint_run_body(record))


def _api_result() -> dict[str, Any]:
    state = get_state()
    with state.lock:
        task = state.task
        if task.running:
            return {"ok": True, "ready": False, "result": None}
        return {"ok": True, "ready": True, "result": task.result}


def handle_api(handler, method: str, path: str) -> bool:
    """处理 /api/...；已处理返回 True。"""
    parsed = urlparse(path)
    if not parsed.path.startswith("/api/"):
        return False

    route = parsed.path.rstrip("/") or parsed.path

    try:
        if route == "/api/status" and method == "GET":
            _send_json(handler, HTTPStatus.OK, _api_status())
            return True
        if route == "/api/config" and method == "GET":
            _send_json(handler, HTTPStatus.OK, _api_config())
            return True
        if route == "/api/run" and method == "POST":
            body = _read_json_body(handler)
            _send_json(handler, HTTPStatus.OK, _api_run(body))
            return True
        if route == "/api/progress" and method == "GET":
            _send_json(handler, HTTPStatus.OK, _api_progress())
            return True
        if route == "/api/result" and method == "GET":
            _send_json(handler, HTTPStatus.OK, _api_result())
            return True
        if route == "/api/automations" and method == "GET":
            _send_json(handler, HTTPStatus.OK, _api_automations())
            return True
        if route == "/api/scripts" and method == "GET":
            _send_json(handler, HTTPStatus.OK, _api_scripts())
            return True
        if route == "/api/history" and method == "GET":
            script_id = parse_qs(parsed.query).get("script_id", [None])[0]
            _send_json(handler, HTTPStatus.OK, _api_run_history(script_id=script_id))
            return True
        if route.startswith("/api/history/"):
            subpath = route.removeprefix("/api/history/").strip("/")
            if not subpath:
                _send_json(
                    handler,
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "缺少历史记录 ID"},
                )
                return True
            history_id = subpath.split("/")[0]
            if method == "GET":
                _send_json(handler, HTTPStatus.OK, _api_run_history_get(history_id))
                return True
        if route == "/api/blueprints" and method == "GET":
            script_id = parse_qs(parsed.query).get("script_id", [None])[0]
            _send_json(handler, HTTPStatus.OK, _api_blueprints(script_id=script_id))
            return True
        if route == "/api/blueprints" and method == "POST":
            body = _read_json_body(handler)
            _send_json(handler, HTTPStatus.OK, _api_blueprint_save(body))
            return True
        if route.startswith("/api/blueprints/"):
            subpath = route.removeprefix("/api/blueprints/").strip("/")
            if not subpath:
                _send_json(
                    handler,
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "缺少蓝图 ID"},
                )
                return True
            parts = subpath.split("/")
            blueprint_id = parts[0]
            action = parts[1] if len(parts) > 1 else ""
            if action == "run" and method == "POST":
                _send_json(handler, HTTPStatus.OK, _api_blueprint_run(blueprint_id))
                return True
            if not action and method == "GET":
                _send_json(handler, HTTPStatus.OK, _api_blueprint_get(blueprint_id))
                return True
            if not action and method == "DELETE":
                _send_json(handler, HTTPStatus.OK, _api_blueprint_delete(blueprint_id))
                return True
        if route.startswith("/api/scripts/"):
            subpath = route.removeprefix("/api/scripts/").strip("/")
            if not subpath:
                _send_json(
                    handler,
                    HTTPStatus.BAD_REQUEST,
                    {"ok": False, "error": "缺少 Script 实例 ID"},
                )
                return True
            parts = subpath.split("/")
            instance_id = parts[0]
            action = parts[1] if len(parts) > 1 else ""
            if action == "terminal" and method == "GET":
                _send_json(handler, HTTPStatus.OK, _api_script_terminal(instance_id))
                return True
            if action == "variables" and method == "PATCH":
                body = _read_json_body(handler)
                _send_json(handler, HTTPStatus.OK, _api_script_variables(instance_id, body))
                return True
            if action == "start" and method == "POST":
                body = _read_json_body(handler)
                _send_json(handler, HTTPStatus.OK, _api_script_start(instance_id, body))
                return True
            if action == "cancel" and method == "POST":
                body = _read_json_body(handler)
                _send_json(handler, HTTPStatus.OK, _api_script_cancel(instance_id, body))
                return True
            if not action and method == "GET":
                _send_json(handler, HTTPStatus.OK, _api_script(instance_id))
                return True
    except json.JSONDecodeError:
        _send_json(
            handler,
            HTTPStatus.BAD_REQUEST,
            {"ok": False, "error": "无效的 JSON"},
        )
        return True
    except ValueError as exc:
        _send_json(
            handler,
            HTTPStatus.BAD_REQUEST,
            {"ok": False, "error": str(exc)},
        )
        return True

    _send_json(
        handler,
        HTTPStatus.NOT_FOUND,
        {"ok": False, "error": "未知的 API 路径"},
    )
    return True
