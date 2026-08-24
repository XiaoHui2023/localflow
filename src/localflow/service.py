from __future__ import annotations

import asyncio
import shutil
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .executor import Executor
from .ids import new_id
from .models import TERMINAL_STATES, TaskCreate, TaskRecord, TaskState
from .settings import RetentionSettings
from .storage import Store


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _elapsed(task: TaskRecord) -> float | None:
    if task.started_monotonic is None:
        return None
    current = time.monotonic()
    if current < task.started_monotonic:
        return None
    return current - task.started_monotonic


class TaskService:
    def __init__(
        self,
        root: Path,
        store: Store,
        executor: Executor,
        max_concurrency: int = 4,
        on_terminal=None,
        retention: RetentionSettings | None = None,
    ) -> None:
        self.root, self.store, self.executor = root, store, executor
        self.max_concurrency = max_concurrency
        self._scheduler: asyncio.Task[None] | None = None
        self._waiters: dict[str, asyncio.Task[None]] = {}
        self._interrupts: dict[str, asyncio.Task[None]] = {}
        self._wake = asyncio.Event()
        self._stopping = False
        self._on_terminal = on_terminal
        self.retention = retention or RetentionSettings()
        self._last_cleanup = 0.0

    def submit(self, draft: TaskCreate) -> TaskRecord:
        record = self.store.create_task(new_id(), draft)
        self._wake.set()
        return record

    def submit_batch(
        self, template: str, values: dict, drafts: list[TaskCreate]
    ) -> tuple[str, list[TaskRecord]]:
        batch_id = new_id()
        task_drafts = [(new_id(), draft) for draft in drafts]
        records = self.store.create_batch(batch_id, template, values, task_drafts)
        self._wake.set()
        return batch_id, records

    def _terminal(self) -> None:
        if self._on_terminal:
            self._on_terminal()

    async def start(self) -> None:
        self._stopping = False
        await self.recover()
        self.maintain()
        self._scheduler = asyncio.create_task(self._loop(), name="localflow-scheduler")

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._scheduler:
            await self._scheduler
        observers = [*self._waiters.values(), *self._interrupts.values()]
        for observer in observers:
            observer.cancel()
        if observers:
            await asyncio.gather(*observers, return_exceptions=True)

    async def recover(self) -> None:
        for task in self.store.list_tasks(
            states=["starting", "running"], limit=500, ascending=True
        ):
            completed_code = await self.executor.completed_code(task.id)
            if completed_code is not None:
                state = TaskState.SUCCEEDED if completed_code == 0 else TaskState.FAILED
                if task.interrupt_stage and completed_code != 0:
                    state = TaskState.CANCELLED
                log = self.root / "logs" / task.id / "output.log"
                self.store.transition(
                    task.id,
                    [TaskState.STARTING, TaskState.RUNNING],
                    state,
                    ended_at=_now(),
                    exit_code=completed_code,
                    log_size=log.stat().st_size if log.exists() else 0,
                    elapsed_seconds=_elapsed(task),
                )
                self._terminal()
            elif await self.executor.is_running(task):
                self._waiters[task.id] = asyncio.create_task(self._wait(task.id))
            elif task.interrupt_stage == "sigkill":
                self.store.transition(
                    task.id,
                    [TaskState.STARTING, TaskState.RUNNING],
                    TaskState.CANCELLED,
                    ended_at=_now(),
                    exit_code=137,
                    elapsed_seconds=_elapsed(task),
                )
                self._terminal()
            else:
                self.store.transition(
                    task.id,
                    [TaskState.STARTING, TaskState.RUNNING],
                    TaskState.LOST,
                    ended_at=_now(),
                )
                self._terminal()

    async def _loop(self) -> None:
        while not self._stopping:
            if time.monotonic() - self._last_cleanup >= self.retention.cleanup_interval_seconds:
                self.maintain()
            await self._schedule()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), 0.5)
            self._wake.clear()

    def maintain(self, now: datetime | None = None) -> dict[str, int]:
        now = now or datetime.now(UTC)
        log_before = (now - timedelta(days=self.retention.log_days)).isoformat()
        task_before = (now - timedelta(days=self.retention.task_days)).isoformat()
        event_before = (now - timedelta(days=self.retention.event_days)).isoformat()
        log_ids = self.store.terminal_task_ids_before(log_before)
        deleted_ids = self.store.purge_retention(
            tasks_before=task_before,
            events_before=event_before,
            idempotency_before=event_before,
        )
        logs_root = (self.root / "logs").resolve()
        removed = 0
        for task_id in set(log_ids) | set(deleted_ids):
            task_log = (logs_root / task_id).resolve()
            if task_log.parent == logs_root and task_log.is_dir():
                shutil.rmtree(task_log)
                removed += 1
        self._last_cleanup = time.monotonic()
        return {"tasks": len(deleted_ids), "log_directories": removed}

    async def _schedule(self) -> None:
        active = self.store.list_tasks(states=["starting", "running"], limit=500)
        capacity = max(0, self.max_concurrency - len(active))
        holders: dict[str, list[str]] = {}
        for task in active:
            for key in task.mutex_keys:
                holders.setdefault(key, []).append(task.id)
        held = set(holders)
        for task in self.store.list_tasks(states=["queued"], limit=500, ascending=True):
            if not capacity:
                break
            if held.intersection(task.mutex_keys):
                blocked_keys = sorted(held.intersection(task.mutex_keys))
                blockers = [owner for key in task.mutex_keys for owner in holders.get(key, [])]
                self.store.set_blocked_by(task.id, blockers, blocked_keys)
                continue
            self.store.set_blocked_by(task.id, [], [])
            if self.store.transition(task.id, [TaskState.QUEUED], TaskState.STARTING):
                for key in task.mutex_keys:
                    holders.setdefault(key, []).append(task.id)
                held.update(task.mutex_keys)
                asyncio.create_task(self._start(task.id))
                capacity -= 1

    async def _start(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        try:
            result = await self.executor.start(task, self.root / "logs" / task.id / "output.log")
        except Exception as exc:
            self.store.append_event(task.id, "task.start_error", {"error": str(exc)})
            self.store.transition(
                task.id, [TaskState.STARTING], TaskState.FAILED, ended_at=_now(), exit_code=127
            )
            self._terminal()
            self._wake.set()
            return
        self.store.transition(
            task.id,
            [TaskState.STARTING],
            TaskState.RUNNING,
            started_at=_now(),
            started_monotonic=time.monotonic(),
            pid=result.pid,
            executor_ref=result.reference,
        )
        self._waiters[task.id] = asyncio.create_task(self._wait(task.id))

    async def _wait(self, task_id: str) -> None:
        try:
            code = await self.executor.wait(task_id)
            task = self.store.get_task(task_id)
            if task.state in TERMINAL_STATES:
                return
            state = TaskState.SUCCEEDED if code == 0 else TaskState.FAILED
            if task.interrupt_stage and code != 0:
                state = TaskState.CANCELLED
            log = self.root / "logs" / task_id / "output.log"
            self.store.transition(
                task_id,
                [TaskState.RUNNING, TaskState.STARTING],
                state,
                ended_at=_now(),
                exit_code=code,
                log_size=log.stat().st_size if log.exists() else 0,
                elapsed_seconds=_elapsed(task),
            )
            self._terminal()
        except Exception as exc:
            self.store.append_event(task_id, "task.wait_error", {"error": str(exc)})
            self.store.transition(
                task_id, [TaskState.RUNNING, TaskState.STARTING], TaskState.LOST, ended_at=_now()
            )
            self._terminal()
        finally:
            self._waiters.pop(task_id, None)
            self._wake.set()

    async def interrupt(
        self, task_id: str, sigint_grace: float = 20, sigterm_grace: float = 10
    ) -> TaskRecord:
        task = self.store.get_task(task_id)
        if task.state == TaskState.QUEUED:
            self.store.transition(
                task_id,
                [TaskState.QUEUED],
                TaskState.CANCELLED,
                ended_at=_now(),
                interrupt_stage="queued",
            )
            self._terminal()
        elif (
            task.state in {TaskState.STARTING, TaskState.RUNNING}
            and task_id not in self._interrupts
        ):
            self._interrupts[task_id] = asyncio.create_task(
                self._interrupt_sequence(task_id, sigint_grace, sigterm_grace)
            )
        return self.store.get_task(task_id)

    async def _interrupt_sequence(
        self, task_id: str, sigint_grace: float, sigterm_grace: float
    ) -> None:
        try:
            for stage, delay in (
                ("sigint", sigint_grace),
                ("sigterm", sigterm_grace),
                ("sigkill", 0),
            ):
                current = self.store.get_task(task_id)
                if current.state in TERMINAL_STATES:
                    return
                self.store.transition(
                    task_id,
                    [TaskState.STARTING, TaskState.RUNNING],
                    current.state,
                    interrupt_stage=stage,
                )
                await self.executor.interrupt(task_id, stage)
                if delay:
                    await asyncio.sleep(delay)
        finally:
            self._interrupts.pop(task_id, None)

    def read_log(self, task_id: str, offset: int = 0, limit: int = 262144) -> tuple[bytes, int]:
        self.store.get_task(task_id)
        path = self.root / "logs" / task_id / "output.log"
        if not path.exists():
            return b"", offset
        with path.open("rb") as stream:
            stream.seek(max(offset, 0))
            data = stream.read(min(max(limit, 1), 1048576))
            return data, stream.tell()

    async def write_terminal(self, task_id: str, data: bytes) -> bool:
        task = self.store.get_task(task_id)
        if task.state not in {TaskState.STARTING, TaskState.RUNNING}:
            return False
        return await self.executor.write(task_id, data)

    async def resize_terminal(self, task_id: str, rows: int, cols: int) -> bool:
        task = self.store.get_task(task_id)
        if task.state not in {TaskState.STARTING, TaskState.RUNNING}:
            return False
        if not (2 <= rows <= 1000 and 2 <= cols <= 1000):
            return False
        return await self.executor.resize(task_id, rows, cols)
