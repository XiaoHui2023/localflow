from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from localflow.executor import SubprocessExecutor
from localflow.models import TaskCreate, TaskState
from localflow.service import TaskService
from localflow.storage import Store

CURRENT = "11111111-1111-4111-8111-111111111111"
PREVIOUS = "22222222-2222-4222-8222-222222222222"


def boot(monkeypatch, value=CURRENT):
    original = Path.read_text

    def read(path, *args, **kwargs):
        if str(path).replace("\\", "/") == "/proc/sys/kernel/random/boot_id":
            if value is None:
                raise FileNotFoundError("boot ID unavailable")
            return value
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)


def task_in(store, root, name, state, **fields):
    task = store.create_task(name, TaskCreate(
        name=name, working_directory=str(root), command=["true"],
    ))
    if state != TaskState.QUEUED:
        store.transition(task.id, [TaskState.QUEUED], state, **fields)
    return task.id


@pytest.mark.asyncio
async def test_new_host_boot_settles_all_active_states_without_querying_reused_owners(
    tmp_path, monkeypatch,
):
    boot(monkeypatch)
    marker = tmp_path / "runtime/host-boot.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps({"version": 1, "boot_id": PREVIOUS}))
    store = Store(tmp_path / "runtime/localflow.db")
    active = [task_in(store, tmp_path, state.value, state, interrupt_stage="sigkill")
              for state in [TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING]]
    history = [task_in(store, tmp_path, state.value, state)
               for state in [TaskState.QUEUED, TaskState.SUCCEEDED, TaskState.FAILED,
                             TaskState.CANCELLED, TaskState.LOST]]
    before = [store.get_task(key).model_dump() for key in history]
    executor = SubprocessExecutor()
    executor.is_running = AsyncMock(side_effect=AssertionError("old boot owner must not be trusted"))
    executor.completed_code = AsyncMock(return_value=0)
    service = TaskService(tmp_path, store, executor)
    await service.recover()
    assert all(store.get_task(key).state == "lost" for key in active)
    assert all(store.get_task(key).status.finished for key in active)
    assert all(store.get_task(key).ended_at is not None for key in active)
    assert before == [store.get_task(key).model_dump() for key in history]
    executor.is_running.assert_not_awaited()
    executor.completed_code.assert_not_awaited()
    assert json.loads(marker.read_text())["boot_id"] == CURRENT
    assert all(any(event.kind == "task.host_restarted" for event in store.events_after(0)
                   if event.task_id == key) for key in active)
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt", [None, "{broken", "[]", '{"version":1,"boot_id":42}',
                                  json.dumps({"version": 1, "boot_id": CURRENT})])
async def test_same_boot_or_legacy_receipt_waits_for_group_after_main_exit(
    tmp_path, monkeypatch, receipt,
):
    boot(monkeypatch)
    store = Store(tmp_path / "runtime/localflow.db")
    key = task_in(store, tmp_path, "still-owned", TaskState.RUNNING)
    if receipt is not None:
        (tmp_path / "runtime/host-boot.json").write_text(receipt)
    executor = SubprocessExecutor()
    executor.completed_code = AsyncMock(return_value=0)
    executor.is_running = AsyncMock(return_value=True)
    finished = asyncio.Event()

    async def wait(_task_id):
        await finished.wait()
        return 0

    executor.wait = wait
    service = TaskService(tmp_path, store, executor)
    await service.recover()
    assert store.get_task(key).state == "running"
    assert key in service._waiters
    finished.set()
    await service._waiters[key]
    assert store.get_task(key).state == "succeeded"
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected", [(None, "lost"), (0, "succeeded"), (7, "failed")])
async def test_legacy_dead_owner_reconciles_without_requiring_old_boot_receipt(
    tmp_path, monkeypatch, code, expected,
):
    boot(monkeypatch, None)
    store = Store(tmp_path / "runtime/localflow.db")
    key = task_in(store, tmp_path, "dead", TaskState.RUNNING)
    executor = SubprocessExecutor()
    executor.completed_code = AsyncMock(return_value=code)
    executor.is_running = AsyncMock(return_value=False)
    await TaskService(tmp_path, store, executor).recover()
    assert store.get_task(key).state == expected
    assert not (tmp_path / "runtime/host-boot.json").exists()
    store.close()
