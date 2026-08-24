from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _signed_headers(client: TestClient, root: Path, body: bytes) -> dict[str, str]:
    challenge = client.post("/api/v1/auth/challenges").json()
    created = str(int(time.time()))
    digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        (
            "POST",
            "/api/v1/tasks",
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
    code = (root / "secrets" / "admin-bootstrap").read_text(encoding="ascii").strip()
    login = client.post("/api/v1/auth/local-sessions", json={"code": code})
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


def test_cookie_admin_writes_require_same_origin_and_csrf(
    client: TestClient, root: Path
) -> None:
    code = (root / "secrets" / "admin-bootstrap").read_text(encoding="ascii").strip()
    login = client.post("/api/v1/auth/local-sessions", json={"code": code})
    csrf = login.json()["csrf_token"]
    payload = {
        "name": "browser-admin",
        "working_directory": str(root),
        "command": ["echo", "ok"],
    }
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
    code = (root / "secrets" / "admin-bootstrap").read_text(encoding="ascii").strip()
    client.post("/api/v1/auth/local-sessions", json={"code": code})
    with pytest.raises(WebSocketDisconnect) as cross_origin, client.websocket_connect(
        "/api/v1/tasks/missing/terminal",
        headers={"Origin": "https://attacker.invalid"},
    ):
        pass
    assert cross_origin.value.code == 4403
