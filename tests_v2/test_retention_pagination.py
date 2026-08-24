from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from localflow.cli import _endpoint
from localflow.models import TaskCreate, TaskState
from localflow.service import TaskService, _elapsed
from localflow.settings import RetentionSettings, ServerSettings, Settings, validate_deployment
from localflow.storage import Store


class NoopExecutor:
    pass


def _draft(root: Path, name: str) -> TaskCreate:
    return TaskCreate(name=name, working_directory=str(root), command=["true"])


def test_endpoint_formats_ipv4_and_ipv6() -> None:
    assert _endpoint("http", "127.0.0.1", 1234) == "http://127.0.0.1:1234"
    assert _endpoint("https", "::1", 443) == "https://[::1]:443"


def test_retention_removes_expired_terminal_data_but_keeps_newer_history(root: Path) -> None:
    store = Store(root / "runtime" / "localflow.db")
    now = datetime.now(UTC)
    old = store.create_task("old", _draft(root, "old"))
    recent = store.create_task("recent", _draft(root, "recent"))
    active = store.create_task("active", _draft(root, "active"))
    store.transition(
        old.id,
        [TaskState.QUEUED],
        TaskState.SUCCEEDED,
        ended_at=(now - timedelta(days=10)).isoformat(),
        exit_code=0,
    )
    store.transition(
        recent.id,
        [TaskState.QUEUED],
        TaskState.SUCCEEDED,
        ended_at=(now - timedelta(days=2)).isoformat(),
        exit_code=0,
    )
    for task_id in (old.id, recent.id, active.id):
        path = root / "logs" / task_id / "output.log"
        path.parent.mkdir(parents=True)
        path.write_text("log", encoding="utf-8")
    service = TaskService(
        root,
        store,
        NoopExecutor(),  # type: ignore[arg-type]
        retention=RetentionSettings(task_days=5, log_days=1, event_days=30),
    )
    result = service.maintain(now)
    assert result == {"tasks": 1, "log_directories": 2}
    with pytest.raises(KeyError):
        store.get_task(old.id)
    assert store.get_task(recent.id).state == TaskState.SUCCEEDED
    assert store.get_task(active.id).state == TaskState.QUEUED
    assert not (root / "logs" / recent.id).exists()
    assert (root / "logs" / active.id / "output.log").exists()
    store.close()


def test_task_api_cursor_is_stable_and_rejects_invalid_cursor(
    admin: TestClient, root: Path
) -> None:
    ids = []
    for name in ("one", "two", "three"):
        response = admin.post(
            "/api/v1/tasks",
            json={"name": name, "working_directory": str(root), "command": ["true"]},
        )
        ids.append(response.json()["task_id"])
    first = admin.get("/api/v1/tasks?limit=2").json()
    assert [item["id"] for item in first["items"]] == list(reversed(ids[1:]))
    assert first["next_cursor"]
    admin.post(
        "/api/v1/tasks",
        json={"name": "new", "working_directory": str(root), "command": ["true"]},
    )
    second = admin.get(
        "/api/v1/tasks", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [item["id"] for item in second["items"]] == [ids[0]]
    assert admin.get("/api/v1/tasks?cursor=not-base64").status_code == 422


def test_non_loopback_requires_tls_files_and_trusted_proxy(tmp_path: Path) -> None:
    settings = Settings(server=ServerSettings(bind="0.0.0.0"))
    with pytest.raises(ValueError, match="TLS files"):
        validate_deployment(settings)
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("test", encoding="ascii")
    key.write_text("test", encoding="ascii")
    valid = Settings(
        server=ServerSettings(
            bind="0.0.0.0",
            tls_certfile=str(cert),
            tls_keyfile=str(key),
            trusted_proxies=["127.0.0.1/32"],
        )
    )
    validate_deployment(valid)
    valid.server.trusted_proxies = ["not-a-network"]
    with pytest.raises(ValueError, match="invalid trusted proxy"):
        validate_deployment(valid)


def test_elapsed_time_uses_monotonic_clock_even_if_wall_start_is_in_future(root: Path) -> None:
    store = Store(root / "runtime" / "localflow.db")
    task = store.create_task("clock", _draft(root, "clock"))
    store.transition(
        task.id,
        [TaskState.QUEUED],
        TaskState.RUNNING,
        started_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
        started_monotonic=time.monotonic() - 5,
    )
    elapsed = _elapsed(store.get_task(task.id))
    assert elapsed is not None and 4.9 <= elapsed < 6
    store.close()
