from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from localflow.api import create_app
from localflow.settings import ExecutionSettings, ServerSettings, Settings


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "root"


@pytest.fixture
def client(root: Path):
    settings = Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(
            backend="subprocess",
            max_concurrency=2,
            sigint_grace_seconds=0.05,
            sigterm_grace_seconds=0.05,
        ),
    )
    app = create_app(root, settings=settings, start_scheduler=False)
    with TestClient(app) as value:
        yield value


@pytest.fixture
def admin(client: TestClient, root: Path) -> TestClient:
    code = (root / "secrets" / "admin-bootstrap").read_text(encoding="ascii").strip()
    response = client.post("/api/v1/auth/local-sessions", json={"code": code})
    assert response.status_code == 200
    client.headers.update(
        {
            "Origin": "http://testserver",
            "X-CSRF-Token": response.json()["csrf_token"],
        }
    )
    return client
