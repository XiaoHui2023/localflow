from __future__ import annotations

import asyncio
import base64
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from localflow.api import create_app
from localflow.executor import SubprocessExecutor
from localflow.models import TaskCreate
from localflow.service import TaskService
from localflow.settings import ExecutionSettings, ServerSettings, Settings
from localflow.storage import Store


@pytest.mark.asyncio
async def test_terminal_input_reaches_process(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="stdin",
            working_directory=str(root),
            command=[sys.executable, "-c", "print(input(), flush=True)"],
        )
    )
    await service.start()
    for _ in range(100):
        await asyncio.sleep(0.01)
        if store.get_task(task.id).state == "running":
            break
    assert await service.write_terminal(task.id, b"interactive-value\n")
    for _ in range(100):
        await asyncio.sleep(0.01)
        if store.get_task(task.id).ended_at:
            break
    assert b"interactive-value" in service.read_log(task.id)[0]
    complete, end = service.read_log(task.id, 0, 1024)
    first, middle = service.read_log(task.id, 0, 5)
    remainder, resumed_end = service.read_log(task.id, middle, end - middle)
    assert first + remainder == complete
    assert resumed_end == end
    await service.stop()
    store.close()


def test_terminal_http_api_controls_and_fresh_offset_log(root: Path) -> None:
    settings = Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(backend="subprocess", max_concurrency=1),
    )
    app = create_app(root, settings=settings, start_scheduler=True)
    with TestClient(
        app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        key = (root / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
        session = client.post("/api/v1/auth/local-sessions", json={"key": key}).json()
        client.headers.update(
            {"Origin": "http://127.0.0.1", "X-CSRF-Token": session["csrf_token"]}
        )
        created = client.post(
            "/api/v1/tasks",
            json={
                "name": "terminal-api",
                "working_directory": str(root),
                "command": [
                    sys.executable,
                    "-u",
                    "-c",
                    "import signal,sys; "
                    "signal.signal(signal.SIGINT,lambda *_: "
                    "(print('control-3',flush=True),sys.exit(0))); "
                    "print('ready',flush=True); value=sys.stdin.read(1); "
                    "print('control-'+str(ord(value)),flush=True)",
                ],
            },
        ).json()
        task_id = created["task_id"]
        deadline = time.monotonic() + 5
        first = None
        while time.monotonic() < deadline:
            first = client.get(f"/api/v1/tasks/{task_id}/logs?offset=0&limit=1024").json()
            if b"ready" in base64.b64decode(first["data"]).splitlines():
                break
            time.sleep(0.02)
        assert first is not None
        assert first["next_offset"] > 0
        resize = client.post(
            f"/api/v1/tasks/{task_id}/terminal/resize", json={"rows": 42, "cols": 120}
        )
        assert resize.status_code == 200
        assert resize.json() == {"accepted": True, "rows": 42, "cols": 120}
        control = client.post(
            f"/api/v1/tasks/{task_id}/terminal/controls", json={"key": "ctrl_c"}
        )
        assert control.status_code == 200
        deadline = time.monotonic() + 5
        combined = b""
        while time.monotonic() < deadline:
            tail = client.get(
                f"/api/v1/tasks/{task_id}/logs?offset={first['next_offset']}&limit=1024"
            ).json()
            combined = base64.b64decode(tail["data"])
            if b"control-3" in combined:
                break
            time.sleep(0.02)
        assert b"control-3" in combined
        detail = client.get(f"/api/v1/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["name"] == "terminal-api"
        assert detail.json()["state"] == "succeeded"
        rejected = client.post(
            f"/api/v1/tasks/{task_id}/terminal/input", json={"data": "late\n"}
        )
        assert rejected.status_code == 409
        history = client.get(
            f"/api/v1/tasks/{task_id}/logs?offset=0&limit=65536"
        ).json()
        assert b"ready" in base64.b64decode(history["data"])
