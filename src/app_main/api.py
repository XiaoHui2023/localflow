from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any
from urllib.parse import urlparse


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
