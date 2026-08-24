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
    remainder, resumed_end = service.read_log(task.id, middle, 1024)
    assert first + remainder == complete
    assert resumed_end == end
    await service.stop()
    store.close()
