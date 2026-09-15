from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from localflow.api import create_app
from localflow.settings import ExecutionSettings, ServerSettings, Settings


def _settings() -> Settings:
    return Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(backend="subprocess"),
    )


def _login(client: TestClient, root: Path) -> dict[str, str]:
    key = (root / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
    response = client.post("/api/v1/auth/local-sessions", json={"key": key})
    assert response.status_code == 200
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": response.json()["csrf_token"],
    }


def test_shutdown_is_admin_only_and_invokes_controller_once(root: Path) -> None:
    requests: list[str] = []
    app = create_app(
        root,
        settings=_settings(),
        start_scheduler=False,
        request_shutdown=lambda: requests.append("shutdown"),
    )
    with TestClient(app) as client:
        denied = client.post("/api/v1/system/shutdown")
        assert denied.status_code == 403
        assert requests == []

        headers = _login(client, root)
        accepted = client.post("/api/v1/system/shutdown", headers=headers)
        repeated = client.post("/api/v1/system/shutdown", headers=headers)

    assert accepted.status_code == 202
    assert accepted.json() == {"status": "stopping"}
    assert repeated.status_code == 202
    assert requests == ["shutdown"]


def test_shutdown_fails_closed_without_controller_owner(root: Path) -> None:
    app = create_app(root, settings=_settings(), start_scheduler=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/system/shutdown",
            headers=_login(client, root),
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "controller shutdown is unavailable"


def test_web_shutdown_closes_open_terminal_socket(root: Path) -> None:
    app = create_app(
        root,
        settings=_settings(),
        start_scheduler=False,
        request_shutdown=lambda: None,
    )
    app.state.tasks.read_log = lambda _task_id, offset, _limit: (b"", offset)
    with TestClient(app) as client:
        headers = _login(client, root)
        with client.websocket_connect(
            "/api/v1/tasks/idle/terminal?offset=0",
            headers={"Origin": "http://testserver"},
        ) as websocket:
            assert websocket.receive_json()["type"] == "caught_up"
            response = client.post("/api/v1/system/shutdown", headers=headers)
            assert response.status_code == 202
            try:
                websocket.receive_json()
            except WebSocketDisconnect as exc:
                assert exc.code == 1001
            else:
                raise AssertionError("terminal WebSocket stayed open during shutdown")


def test_web_shutdown_closes_open_event_stream_without_browser_refresh(root: Path) -> None:
    """An idle browser SSE connection must not deadlock Uvicorn shutdown."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()

    server: uvicorn.Server | None = None

    def request_shutdown() -> None:
        assert server is not None
        server.should_exit = True

    app = create_app(
        root,
        settings=_settings(),
        start_scheduler=False,
        request_shutdown=request_shutdown,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            log_config=None,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started

    login = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    key = (root / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
    body = ('{"key":"' + key + '"}').encode()
    login.request(
        "POST",
        "/api/v1/auth/local-sessions",
        body=body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    login_response = login.getresponse()
    payload = json.loads(login_response.read())
    cookie = login_response.getheader("Set-Cookie", "").split(";", 1)[0]
    assert login_response.status == 200

    events = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    events.request("GET", "/api/v1/events", headers={"Cookie": cookie})
    event_response = events.getresponse()
    assert event_response.status == 200

    control = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    control.request(
        "POST",
        "/api/v1/system/shutdown",
        body=b"",
        headers={
            "Cookie": cookie,
            "Origin": f"http://127.0.0.1:{port}",
            "X-CSRF-Token": payload["csrf_token"],
            "Content-Length": "0",
        },
    )
    shutdown_response = control.getresponse()
    assert shutdown_response.status == 202
    assert shutdown_response.read()

    thread.join(timeout=5)
    try:
        assert not thread.is_alive()
    finally:
        server.force_exit = True
        events.close()
        control.close()
        login.close()
        thread.join(timeout=2)
