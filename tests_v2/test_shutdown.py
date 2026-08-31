from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

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
