from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from localflow.executor import SubprocessExecutor
from localflow.models import TaskCreate
from localflow.service import TaskService
from localflow.storage import Store


@pytest.mark.asyncio
async def test_mutex_queue_and_logs(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=2)
    command = [sys.executable, "-c", "import time; print('ok', flush=True); time.sleep(.15)"]
    first = service.submit(
        TaskCreate(
            name="one", working_directory=str(root), command=command, mutex_keys=["license:a"]
        )
    )
    second = service.submit(
        TaskCreate(
            name="two", working_directory=str(root), command=command, mutex_keys=["license:a"]
        )
    )
    third = service.submit(
        TaskCreate(
            name="three", working_directory=str(root), command=command, mutex_keys=["license:b"]
        )
    )
    await service.start()
    for _ in range(50):
        await asyncio.sleep(0.01)
        queued = store.get_task(second.id)
        if queued.state == "queued" and queued.blocked_by:
            break
    assert store.get_task(second.id).blocked_by == [first.id]
    assert store.get_task(second.id).blocked_keys == ["license:a"]
    for _ in range(100):
        await asyncio.sleep(0.03)
        if all(store.get_task(item.id).ended_at for item in (first, second, third)):
            break
    await service.stop()
    one, two, three = [store.get_task(item.id) for item in (first, second, third)]
    assert one.state == two.state == three.state == "succeeded"
    assert two.started_at >= one.ended_at
    assert b"ok" in service.read_log(first.id)[0]
    store.close()


@pytest.mark.asyncio
async def test_interrupt_starts_with_sigint(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="long",
            working_directory=str(root),
            command=[sys.executable, "-c", "import time; time.sleep(30)"],
        )
    )
    await service.start()
    for _ in range(50):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).state == "running":
            break
    await service.interrupt(task.id, 0.05, 0.05)
    for _ in range(100):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    assert result.state == "cancelled"
    assert result.interrupt_stage == "sigint"
    await service.stop()
    store.close()
