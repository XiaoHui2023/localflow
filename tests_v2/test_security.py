from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from localflow.api import _initial_event_cursor, _inline_script_csp_hashes, create_app
from localflow.auth import AuthManager
from localflow.settings import ExecutionSettings, ServerSettings, Settings


def _signed_headers(
    client: TestClient,
    root: Path,
    body: bytes,
    *,
    method: str = "POST",
    path: str = "/api/v1/tasks",
) -> dict[str, str]:
    challenge = client.post("/api/v1/auth/challenges").json()
    created = str(int(time.time()))
    digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        (
            method,
            path,
            digest,
            str(challenge["generation"]),
            created,
            challenge["nonce"],
        )
    )
    key = (root / "secrets" / "api-key").read_text(encoding="ascii").strip().encode()
    signature = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-LocalFlow-Nonce": challenge["nonce"],
        "X-LocalFlow-Created": created,
        "X-LocalFlow-Generation": str(challenge["generation"]),
        "X-LocalFlow-Signature": signature,
    }


def test_loopback_is_not_administrator_identity(root: Path) -> None:
    settings = Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(backend="subprocess"),
    )
    app = create_app(root, settings=settings, start_scheduler=False)
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    ) as loopback:
        assert loopback.get("/api/v1/system/status").json()["role"] == "summary"
        assert loopback.get("/api/v1/auth/session").status_code == 401
        assert loopback.get("/api/v1/plugins").status_code == 403
        created = loopback.post(
            "/api/v1/config/files",
            json={"path": "command/direct.yaml", "plugin": "command"},
        )
        assert created.status_code == 403


def test_spa_fallback_never_masks_unknown_api_or_escapes_dist(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "frontend"
    dist.mkdir()
    (dist / "assets").mkdir()
    (dist / "index.html").write_text("<main>app</main>", encoding="utf-8")
    (tmp_path / "private.txt").write_text("private", encoding="utf-8")
    monkeypatch.setenv("LOCALFLOW_WEB_DIST", str(dist))
    settings = Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(backend="subprocess"),
    )
    app = create_app(root, settings=settings, start_scheduler=False)

    with TestClient(app) as browser:
        assert browser.get("/tasks/active").text == "<main>app</main>"
        unknown_api = browser.get("/api/v1/tasks/missing/log")
        assert unknown_api.status_code == 404
        assert unknown_api.headers["content-type"].startswith("application/json")
        assert browser.get("/%2e%2e/private.txt").status_code == 404


def test_final_spa_inline_loader_is_allowed_by_exact_csp_hash(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "frontend"
    dist.mkdir()
    (dist / "assets").mkdir()
    loader = "System.import('./assets/index-legacy.js')"
    index = dist / "index.html"
    index.write_bytes(
        (
            "<script src='./compat-boot.js'></script><main>app</main>"
            "<script id='vite-legacy-entry' data-src='./assets/index-legacy.js'>"
            + loader
            + "</script>"
        ).encode("utf-8")
    )
    expected = "'sha256-" + base64.b64encode(
        hashlib.sha256(loader.encode("utf-8")).digest()
    ).decode() + "'"
    assert _inline_script_csp_hashes(index) == (expected,)

    monkeypatch.setenv("LOCALFLOW_WEB_DIST", str(dist))
    settings = Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(backend="subprocess"),
    )
    app = create_app(root, settings=settings, start_scheduler=False)
    with TestClient(app) as browser:
        policy = browser.get("/").headers["content-security-policy"]
        assert "script-src 'self' " + expected in policy


def test_event_stream_starts_live_but_honours_explicit_resume_cursor(root: Path) -> None:
    settings = Settings(execution=ExecutionSettings(backend="subprocess"))
    app = create_app(root, settings=settings, start_scheduler=False)
    store = app.state.store
    first = store.append_event(None, "config.changed", {"path": "first.yaml"})
    latest = store.append_event(None, "config.changed", {"path": "latest.yaml"})

    assert _initial_event_cursor(store, None, None) == latest
    assert _initial_event_cursor(store, 0, None) == 0
    assert _initial_event_cursor(store, None, str(first)) == first
    assert _initial_event_cursor(store, None, "invalid") == latest


def test_hmac_signature_nonce_replay_and_terminal_rotation(client: TestClient, root: Path) -> None:
    payload = {
        "name": "signed",
        "working_directory": str(root),
        "command": ["echo", "ok"],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = _signed_headers(client, root, body)
    created = client.post("/api/v1/tasks", content=body, headers=headers)
    assert created.status_code == 202
    assert client.post("/api/v1/tasks", content=body, headers=headers).status_code == 403

    old_key = (root / "secrets" / "api-key").read_bytes()
    key = (root / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
    login = client.post("/api/v1/auth/local-sessions", json={"key": key})
    assert login.status_code == 200
    client.headers.update(
        {
            "Origin": "http://testserver",
            "X-CSRF-Token": login.json()["csrf_token"],
        }
    )
    task_id = created.json()["task_id"]
    assert client.post(f"/api/v1/tasks/{task_id}/interrupt").status_code == 200
    assert (root / "secrets" / "api-key").read_bytes() != old_key
    assert client.post("/api/v1/auth/challenges").json()["generation"] == 2


def test_signed_client_can_manage_config_and_use_plugin_run_contract(
    client: TestClient, root: Path
) -> None:
    def request(
        method: str,
        path: str,
        payload: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        body = (
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
            if payload is not None
            else b""
        )
        headers = _signed_headers(client, root, body, method=method, path=path)
        headers.update(extra_headers or {})
        return client.request(method, path, content=body, headers=headers)

    assert client.get("/api/v1/plugins").status_code == 403
    assert client.get("/api/v1/config/files").status_code == 403

    plugins = request("GET", "/api/v1/plugins")
    assert plugins.status_code == 200
    assert all(item["api"]["example"] for item in plugins.json()["items"])

    created = request(
        "POST",
        "/api/v1/config/files",
        {"path": "command/signed.yaml", "plugin": "command"},
    )
    assert created.status_code == 201
    read = request("GET", "/api/v1/config/files/command/signed.yaml")
    assert read.status_code == 200
    assert read.json()["diagnosis"]["runnable"] is True

    content = read.json()["content"].replace("hello-world", "signed-command")
    updated = request(
        "PUT",
        "/api/v1/config/files/command/signed.yaml",
        {"content": content},
        {"If-Match": created.json()["version"]},
    )
    assert updated.status_code == 200
    moved = request(
        "POST",
        "/api/v1/config/files/command/signed.yaml/move",
        {"target": "command/signed-renamed.yaml", "version": updated.json()["version"]},
    )
    assert moved.status_code == 200

    run_payload = {
        "configuration": {
            "plugin": "command",
            "name": "signed-inline",
            "working_directory": str(root),
            "command": ["echo", "signed"],
            "labels": ["signed-api"],
        },
        "inputs": {},
    }
    first_run = request(
        "POST", "/api/v1/runs", run_payload, {"Idempotency-Key": "signed-inline"}
    )
    assert first_run.status_code == 202
    repeated_run = request(
        "POST", "/api/v1/runs", run_payload, {"Idempotency-Key": "signed-inline"}
    )
    assert repeated_run.json() == first_run.json()

    task_id = first_run.json()["task_ids"][0]
    detail = request("GET", f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["command"] == ["echo", "signed"]

    wrong_query_headers = _signed_headers(
        client,
        root,
        b"",
        method="GET",
        path="/api/v1/tasks?label=other&limit=10",
    )
    rejected_query = client.get(
        "/api/v1/tasks?label=signed-api&limit=10", headers=wrong_query_headers
    )
    assert rejected_query.status_code == 403

    listing = request("GET", "/api/v1/tasks?label=signed-api&limit=10")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["command"] == ["echo", "signed"]
    assert request("GET", f"/api/v1/tasks/{task_id}/logs").status_code == 200
    terminal = request(
        "POST", f"/api/v1/tasks/{task_id}/terminal/controls", {"key": "ctrl_c"}
    )
    assert terminal.status_code == 409
    assert request("POST", f"/api/v1/tasks/{task_id}/interrupt").status_code == 200

    deleted = request(
        "DELETE",
        "/api/v1/config/files/command/signed-renamed.yaml",
        extra_headers={"If-Match": moved.json()["version"]},
    )
    assert deleted.status_code == 204


def test_cookie_admin_writes_require_same_origin_and_csrf(
    client: TestClient, root: Path
) -> None:
    key = (root / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
    login = client.post("/api/v1/auth/local-sessions", json={"key": key})
    csrf = login.json()["csrf_token"]
    payload = {
        "name": "browser-admin",
        "working_directory": str(root),
        "command": ["echo", "ok"],
    }
    assert client.get("/api/v1/config/files").status_code == 200
    assert client.post("/api/v1/tasks", json=payload).status_code == 403
    assert (
        client.post(
            "/api/v1/tasks",
            json=payload,
            headers={"Origin": "https://attacker.invalid", "X-CSRF-Token": csrf},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/tasks",
            json=payload,
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
        ).status_code
        == 202
    )
    recovered = client.get("/api/v1/auth/session")
    assert recovered.status_code == 200
    assert recovered.json()["csrf_token"] == csrf


def test_web_key_session_survives_service_restart_until_key_changes(root: Path) -> None:
    settings = Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(backend="subprocess"),
    )
    first_app = create_app(root, settings=settings, start_scheduler=False)
    with TestClient(first_app) as first:
        key_path = root / "secrets" / "web-admin-key"
        key = key_path.read_text(encoding="ascii").strip()
        assert first.post(
            "/api/v1/auth/local-sessions", json={"key": "wrong"}
        ).status_code == 401
        login = first.post("/api/v1/auth/local-sessions", json={"key": key})
        assert login.status_code == 200
        assert login.json()["persistent"] is True
        assert "Max-Age=34560000" in login.headers["set-cookie"]
        assert key_path.read_text(encoding="ascii").strip() == key
        cookie = first.cookies.get("localflow_session")

    restarted_app = create_app(root, settings=settings, start_scheduler=False)
    with TestClient(restarted_app) as restarted:
        restarted.cookies.set("localflow_session", cookie)
        assert restarted.get("/api/v1/system/status").json()["role"] == "admin"
        session = restarted.get("/api/v1/auth/session")
        assert session.status_code == 200
        assert session.json()["persistent"] is True
        assert "Max-Age=34560000" in session.headers["set-cookie"]

        key_path.write_text("replacement-key", encoding="ascii")
        assert restarted.get("/api/v1/system/status").json()["role"] == "summary"
        assert restarted.get("/api/v1/auth/session").status_code == 401


def test_legacy_admin_secret_is_migrated_without_changing_its_value(root: Path) -> None:
    directory = root / "secrets"
    directory.mkdir(parents=True)
    legacy = directory / "admin-bootstrap"
    legacy.write_text("existing-owner-secret", encoding="ascii")
    if os.name != "nt":
        os.chmod(directory, 0o700)
        os.chmod(legacy, 0o600)

    manager = AuthManager(root)

    assert manager.admin_path.name == "web-admin-key"
    assert manager.admin_path.read_text(encoding="ascii") == "existing-owner-secret"
    assert not legacy.exists()


def test_challenge_survives_one_bounded_key_rotation(client: TestClient, root: Path) -> None:
    payload = {
        "name": "rotation-race",
        "working_directory": str(root),
        "command": ["echo", "ok"],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = _signed_headers(client, root, body)
    client.app.state.auth.rotate_api_key()
    client.app.state.auth.rotate_api_key()
    accepted = client.post("/api/v1/tasks", content=body, headers=headers)
    assert accepted.status_code == 202
    assert client.post("/api/v1/tasks", content=body, headers=headers).status_code == 403


def test_summary_and_cross_origin_cookie_cannot_open_terminal(
    client: TestClient, root: Path
) -> None:
    with pytest.raises(WebSocketDisconnect) as anonymous, client.websocket_connect(
        "/api/v1/tasks/missing/terminal"
    ):
        pass
    assert anonymous.value.code == 4403
    key = (root / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
    client.post("/api/v1/auth/local-sessions", json={"key": key})
    with pytest.raises(WebSocketDisconnect) as cross_origin, client.websocket_connect(
        "/api/v1/tasks/missing/terminal",
        headers={"Origin": "https://attacker.invalid"},
    ):
        pass
    assert cross_origin.value.code == 4403


def test_openapi_schema_is_only_available_to_administrator(
    client: TestClient, root: Path
) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
    assert client.get("/api/v1/openapi").status_code == 403
    key = (root / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
    assert client.post("/api/v1/auth/local-sessions", json={"key": key}).status_code == 200
    response = client.get("/api/v1/openapi")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "LocalFlow"
    assert "/api/v1/tasks" in schema["paths"]
    assert "/api/v1/runs" in schema["paths"]
    assert "/api/v1/runs/plan" in schema["paths"]
    assert "/api/v1/plugins" in schema["paths"]
    assert "/api/v1/plugins/{name}" in schema["paths"]
    assert "/api/v1/config/files/{path}" in schema["paths"]
    assert "/api/v1/config/files/{path}/plan" in schema["paths"]
    assert "/api/v1/config/files/{path}/move" in schema["paths"]
    assert "/api/v1/openapi" not in schema["paths"]
