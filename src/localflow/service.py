from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .executor import Executor
from .ids import new_id
from .log_files import MIB, append_lifecycle
from .models import TERMINAL_STATES, StopAction, StopStrategy, TaskCreate, TaskRecord, TaskState
from .settings import LoggingSettings, RetentionSettings
from .storage import Store

logger = logging.getLogger(__name__)


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
        logging_settings: LoggingSettings | None = None,
        result_evaluator=None,
    ) -> None:
        self.root, self.store, self.executor = root, store, executor
        self.max_concurrency = max_concurrency
        self._scheduler: asyncio.Task[None] | None = None
        self._waiters: dict[str, asyncio.Task[None]] = {}
        self._interrupts: dict[str, asyncio.Task[None]] = {}
        self._interrupt_advances: dict[str, asyncio.Event] = {}
        self._wake = asyncio.Event()
        self._stopping = False
        self._on_terminal = on_terminal
        self.retention = retention or RetentionSettings()
        self.logging_settings = logging_settings or LoggingSettings()
        self._result_evaluator = result_evaluator
        self._last_cleanup = 0.0

    def submit(self, draft: TaskCreate) -> TaskRecord:
        record = self.store.create_task(new_id(), draft)
        self._log_lifecycle(
            record,
            "task.queued",
            name=record.name,
            working_directory=record.working_directory,
            command=json.dumps(record.command, ensure_ascii=False),
        )
        name = " ".join(draft.name.split())[:160]
        logger.info("task queued task_id=%s name=%s", record.id, name)
        self._wake.set()
        return record

    def submit_batch(
        self,
        template: str,
        values: dict,
        drafts: list[TaskCreate],
        idempotency: tuple[str, str, str] | None = None,
    ) -> tuple[str, list[TaskRecord]]:
        batch_id = new_id()
        task_drafts = [(new_id(), draft) for draft in drafts]
        response = {
            "batch_id": batch_id,
            "task_ids": [task_id for task_id, _draft in task_drafts],
            "count": len(task_drafts),
        }
        reservation = (*idempotency, response) if idempotency is not None else None
        records, previous = self.store.create_batch(
            batch_id, template, values, task_drafts, reservation
        )
        if previous is not None:
            return str(previous["batch_id"]), records
        for record in records:
            self._log_lifecycle(
                record,
                "task.queued",
                name=record.name,
                working_directory=record.working_directory,
                command=json.dumps(record.command, ensure_ascii=False),
                batch_id=batch_id,
            )
        logger.info("batch queued batch_id=%s tasks=%s template=%s", batch_id, len(records), template)
        self._wake.set()
        return batch_id, records

    def _terminal(self) -> None:
        if self._on_terminal:
            self._on_terminal()

    def _log_lifecycle(self, task: TaskRecord, event: str, **fields: object) -> None:
        path = self.root / "logs" / task.id / "output.log"
        try:
            append_lifecycle(
                path,
                self.logging_settings.task_file_mb * MIB,
                self.logging_settings.keep_free_mb * MIB,
                event,
                task_id=task.id,
                **fields,
            )
        except OSError:
            logger.exception("task lifecycle log could not be written task_id=%s", task.id)

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

    async def shutdown_all(self, timeout_seconds: float = 60) -> None:
        """Stop every queued/running task and verify that no process tree remains."""
        active_states = [TaskState.QUEUED, TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING]
        active = self.store.list_tasks(states=active_states, limit=10_000, ascending=True)
        for task in active:
            await self.interrupt(task.id)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = self.store.list_tasks(states=active_states, limit=10_000, ascending=True)
            if not remaining:
                return
            await asyncio.sleep(0.1)
        remaining = self.store.list_tasks(states=active_states, limit=10_000, ascending=True)
        for task in remaining:
            logger.warning("shutdown force cleanup task_id=%s", task.id)
            await self.executor.interrupt(task.id, "sigkill")
        for task in remaining:
            await self._confirm_forced_exit(task.id)

    async def recover(self) -> None:
        for task in self.store.list_tasks(
            states=["starting", "running", "stopping"], limit=500, ascending=True
        ):
            completed_code = await self.executor.completed_code(task.id)
            if completed_code is not None:
                state = TaskState.SUCCEEDED if completed_code == 0 else TaskState.FAILED
                if task.interrupt_stage:
                    state = TaskState.CANCELLED
                status_override, custom = self._evaluate_result(task, completed_code)
                log = self.root / "logs" / task.id / "output.log"
                self.store.transition(
                    task.id,
                    [TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING],
                    state,
                    ended_at=_now(),
                    exit_code=completed_code,
                    log_size=log.stat().st_size if log.exists() else 0,
                    elapsed_seconds=_elapsed(task),
                    status_override=status_override,
                    custom_json=json.dumps(custom, ensure_ascii=False),
                )
                self._terminal()
            elif await self.executor.is_running(task):
                self._waiters[task.id] = asyncio.create_task(self._wait(task.id))
                if task.interrupt_stage:
                    self._start_interrupt(task, 20, 10)
            elif task.interrupt_stage == "sigkill":
                self.store.transition(
                    task.id,
                    [TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING],
                    TaskState.CANCELLED,
                    ended_at=_now(),
                    exit_code=137,
                    elapsed_seconds=_elapsed(task),
                )
                self._terminal()
            else:
                self.store.transition(
                    task.id,
                    [TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING],
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
        task_before = (now - timedelta(days=self.retention.task_days)).isoformat()
        event_before = task_before
        deleted_ids = self.store.purge_retention(
            tasks_before=task_before,
            events_before=event_before,
            idempotency_before=event_before,
        )
        logs_root = (self.root / "logs").resolve()
        logs_root.mkdir(parents=True, exist_ok=True)
        removed = 0
        for task_id in set(deleted_ids):
            task_log = (logs_root / task_id).resolve()
            if task_log.parent == logs_root and task_log.is_dir():
                shutil.rmtree(task_log)
                removed += 1
                self.store.set_log_size(task_id, 0)
        total_limit = self.logging_settings.task_total_mb * MIB
        task_directories = [
            path for path in logs_root.iterdir() if path.is_dir() and path.name != "service"
        ]
        total_size = sum(
            file.stat().st_size
            for directory in task_directories
            for file in directory.rglob("*")
            if file.is_file()
        )
        for task_id in self.store.terminal_task_ids_oldest():
            if total_size <= total_limit:
                break
            task_log = (logs_root / task_id).resolve()
            if task_log.parent != logs_root or not task_log.is_dir():
                continue
            size = sum(file.stat().st_size for file in task_log.rglob("*") if file.is_file())
            shutil.rmtree(task_log)
            total_size -= size
            removed += 1
            self.store.set_log_size(task_id, 0)
        instances = (self.root / "runtime" / "instances").resolve()
        for task_id in set(deleted_ids):
            for suffix in (".json", ".exit", ".sock"):
                candidate = (instances / f"{task_id}{suffix}").resolve()
                if candidate.parent == instances:
                    candidate.unlink(missing_ok=True)
        self._last_cleanup = time.monotonic()
        logger.debug(
            "retention complete tasks=%s log_directories=%s task_log_bytes=%s",
            len(deleted_ids),
            removed,
            total_size,
        )
        return {"tasks": len(deleted_ids), "log_directories": removed}

    async def _schedule(self) -> None:
        active = self.store.list_tasks(states=["starting", "running", "stopping"], limit=500)
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
            if self.store.transition(
                task.id,
                [TaskState.QUEUED],
                TaskState.STARTING,
                started_at=_now(),
                started_monotonic=time.monotonic(),
            ):
                for key in task.mutex_keys:
                    holders.setdefault(key, []).append(task.id)
                held.update(task.mutex_keys)
                asyncio.create_task(self._start(task.id))
                capacity -= 1

    async def _start(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        self._log_lifecycle(task, "task.starting", backend=type(self.executor).__name__)
        try:
            result = await self.executor.start(task, self.root / "logs" / task.id / "output.log")
        except Exception as exc:
            logger.error("task failed to start task_id=%s", task.id)
            logger.debug("task start exception task_id=%s", task.id, exc_info=True)
            self.store.append_event(task.id, "task.start_error", {"error": str(exc)})
            self._log_lifecycle(
                task,
                "task.start_failed",
                error=f"{type(exc).__name__}: {exc}",
            )
            log = self.root / "logs" / task.id / "output.log"
            self.store.transition(
                task.id,
                [TaskState.STARTING],
                TaskState.FAILED,
                ended_at=_now(),
                exit_code=127,
                log_size=log.stat().st_size if log.exists() else 0,
                elapsed_seconds=_elapsed(task),
            )
            self._terminal()
            self._wake.set()
            return
        self.store.transition(
            task.id,
            [TaskState.STARTING],
            TaskState.RUNNING,
            pid=result.pid,
            executor_ref=result.reference,
        )
        logger.info("task started task_id=%s", task.id)
        self._waiters[task.id] = asyncio.create_task(self._wait(task.id))

    async def _wait(self, task_id: str) -> None:
        try:
            code = await self.executor.wait(task_id)
            task = self.store.get_task(task_id)
            if task.state in TERMINAL_STATES:
                return
            state = TaskState.SUCCEEDED if code == 0 else TaskState.FAILED
            if task.interrupt_stage:
                state = TaskState.CANCELLED
            status_override, custom = self._evaluate_result(task, code)
            log = self.root / "logs" / task_id / "output.log"
            self.store.transition(
                task_id,
                [TaskState.RUNNING, TaskState.STARTING, TaskState.STOPPING],
                state,
                ended_at=_now(),
                exit_code=code,
                log_size=log.stat().st_size if log.exists() else 0,
                elapsed_seconds=_elapsed(task),
                status_override=status_override,
                custom_json=json.dumps(custom, ensure_ascii=False),
            )
            logger.info("task finished task_id=%s state=%s exit_code=%s", task_id, state, code)
            self._terminal()
        except Exception as exc:
            logger.error("task result could not be collected task_id=%s", task_id)
            logger.debug("task wait exception task_id=%s", task_id, exc_info=True)
            self.store.append_event(task_id, "task.wait_error", {"error": str(exc)})
            self.store.transition(
                task_id,
                [TaskState.RUNNING, TaskState.STARTING, TaskState.STOPPING],
                TaskState.LOST,
                ended_at=_now(),
            )
            self._terminal()
        finally:
            self._waiters.pop(task_id, None)
            self._wake.set()

    def _evaluate_result(self, task: TaskRecord, code: int):
        if task.interrupt_stage or not self._result_evaluator:
            return None, task.custom
        try:
            evaluated = self._result_evaluator(
                task.model_copy(update={"exit_code": code}),
                {"root": str(self.root)},
            )
            return evaluated if evaluated else (None, task.custom)
        except Exception as exc:
            logger.error("plugin result evaluation failed task_id=%s error=%s", task.id, exc)
            self.store.append_event(task.id, "task.result_evaluation_error", {"error": str(exc)})
            return None, task.custom

    async def interrupt(
        self, task_id: str, sigint_grace: float = 20, sigterm_grace: float = 10
    ) -> TaskRecord:
        task = self.store.get_task(task_id)
        if task.state == TaskState.QUEUED:
            logger.info("queued task cancelled task_id=%s", task_id)
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
            if task.stop is None:
                self.store.snapshot_stop(
                    task_id,
                    StopStrategy(
                        actions=[
                            StopAction(
                                type="signal", signal="SIGINT", timeout_seconds=sigint_grace
                            ),
                            StopAction(
                                type="signal", signal="SIGTERM", timeout_seconds=sigterm_grace
                            ),
                        ]
                    ),
                )
                task = self.store.get_task(task_id)
            self.store.transition(
                task_id,
                [TaskState.STARTING, TaskState.RUNNING],
                TaskState.STOPPING,
                interrupt_stage="requested",
            )
            task = self.store.get_task(task_id)
            self._start_interrupt(task, sigint_grace, sigterm_grace)
            logger.info("task stop requested task_id=%s", task_id)
        elif task_id in self._interrupt_advances:
            self._interrupt_advances[task_id].set()
            self.store.append_event(task_id, "task.interrupt_advanced", {})
            logger.info("task stop advanced task_id=%s", task_id)
        return self.store.get_task(task_id)

    def _start_interrupt(self, task: TaskRecord, sigint_grace: float, sigterm_grace: float) -> None:
        advance = asyncio.Event()
        self._interrupt_advances[task.id] = advance
        self._interrupts[task.id] = asyncio.create_task(
            self._interrupt_sequence(task.id, sigint_grace, sigterm_grace, advance)
        )

    async def _interrupt_sequence(
        self,
        task_id: str,
        sigint_grace: float,
        sigterm_grace: float,
        advance: asyncio.Event,
    ) -> None:
        try:
            task = self.store.get_task(task_id)
            actions = (
                task.stop.actions
                if task.stop
                else [
                    StopAction(type="signal", signal="SIGINT", timeout_seconds=sigint_grace),
                    StopAction(type="signal", signal="SIGTERM", timeout_seconds=sigterm_grace),
                ]
            )
            start_index = self._interrupted_action_index(task.interrupt_stage)
            for index, action in enumerate(actions[start_index:], start=start_index):
                current = self.store.get_task(task_id)
                if current.state in TERMINAL_STATES:
                    return
                stage = f"stop:{index}:{action.type}"
                self.store.transition(
                    task_id,
                    [TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING],
                    TaskState.STOPPING,
                    interrupt_stage=stage,
                )
                log_path = self.root / "logs" / task_id / "output.log"
                offset = log_path.stat().st_size if log_path.exists() else 0
                remaining = await self._apply_stop_action(current, action)
                await self._wait_stop_action(task_id, action, offset, advance, remaining)
            current = self.store.get_task(task_id)
            # systemd may need one scheduler tick to publish the exit file and
            # empty the control group after the last graceful action returned.
            for _ in range(10):
                if current.state in TERMINAL_STATES:
                    return
                await asyncio.sleep(0.05)
                current = self.store.get_task(task_id)
            if current.state not in TERMINAL_STATES:
                logger.warning("task stop escalated to force cleanup task_id=%s", task_id)
                self.store.transition(
                    task_id,
                    [TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING],
                    TaskState.STOPPING,
                    interrupt_stage="sigkill",
                )
                await self.executor.interrupt(task_id, "sigkill")
                await self._confirm_forced_exit(task_id)
        finally:
            self._interrupts.pop(task_id, None)
            self._interrupt_advances.pop(task_id, None)

    @staticmethod
    def _interrupted_action_index(stage: str | None) -> int:
        if not stage or not stage.startswith("stop:"):
            return 0
        try:
            return max(0, int(stage.split(":", 2)[1]))
        except (ValueError, IndexError):
            return 0

    async def _apply_stop_action(self, task: TaskRecord, action: StopAction) -> float:
        started = time.monotonic()
        if action.type == "signal":
            stage = "sigint" if action.signal == "SIGINT" else "sigterm"
            await self.executor.interrupt(task.id, stage)
        elif action.type == "input":
            await self.executor.write(task.id, action.data.encode())
        else:
            process = await asyncio.create_subprocess_exec(
                *action.command,
                cwd=task.working_directory,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=os.name != "nt",
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=action.timeout_seconds)
            except TimeoutError:
                if os.name != "nt":
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                await process.wait()
        return max(0, action.timeout_seconds - (time.monotonic() - started))

    async def _wait_stop_action(
        self,
        task_id: str,
        action: StopAction,
        offset: int,
        advance: asyncio.Event,
        timeout_seconds: float,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        needle = action.output_contains.encode() if action.output_contains else None
        tail = b""
        advance.clear()
        while time.monotonic() < deadline:
            if self.store.get_task(task_id).state in TERMINAL_STATES:
                return
            if advance.is_set():
                advance.clear()
                return
            if needle:
                chunk, offset = self.read_log(task_id, offset, 65536)
                tail = (tail + chunk)[-max(len(needle) * 2, 1024) :]
                if needle in tail:
                    return
            await asyncio.sleep(0.05)

    async def _confirm_forced_exit(self, task_id: str) -> None:
        """Keep ownership until the real process tree is gone; never report a guessed exit."""
        attempt = 0
        while not self._stopping:
            current = self.store.get_task(task_id)
            if current.state in TERMINAL_STATES:
                return
            await asyncio.sleep(min(2.0 + attempt, 10.0))
            current = self.store.get_task(task_id)
            if current.state in TERMINAL_STATES:
                return
            try:
                running = await self.executor.is_running(current)
                completed = await self.executor.completed_code(task_id)
            except Exception as exc:
                self.store.append_event(
                    task_id,
                    "task.exit_confirmation_error",
                    {"attempt": attempt + 1, "error": str(exc)},
                )
                running, completed = True, None
            if completed is not None and not running:
                log = self.root / "logs" / task_id / "output.log"
                if self.store.transition(
                    task_id,
                    [TaskState.STOPPING],
                    TaskState.CANCELLED,
                    ended_at=_now(),
                    exit_code=completed,
                    log_size=log.stat().st_size if log.exists() else 0,
                    elapsed_seconds=_elapsed(current),
                ):
                    logger.info(
                        "forced task exit confirmed task_id=%s exit_code=%s", task_id, completed
                    )
                    self._terminal()
                    self._wake.set()
                return
            attempt += 1
            self.store.append_event(
                task_id,
                "task.force_cleanup_retry",
                {"attempt": attempt, "process_tree_running": running},
            )
            logger.error(
                "task process tree still awaiting confirmed exit task_id=%s attempt=%s",
                task_id,
                attempt,
            )
            await self.executor.interrupt(task_id, "sigkill")

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
        if task.state not in {TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING}:
            return False
        return await self.executor.write(task_id, data)

    async def resize_terminal(self, task_id: str, rows: int, cols: int) -> bool:
        task = self.store.get_task(task_id)
        if task.state not in {TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING}:
            return False
        if not (2 <= rows <= 1000 and 2 <= cols <= 1000):
            return False
        return await self.executor.resize(task_id, rows, cols)
