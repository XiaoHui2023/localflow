from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .executor import Executor
from .ids import new_id
from .log_files import MIB, append_lifecycle
from .models import (
    TERMINAL_STATES,
    StopAction,
    StopStrategy,
    TaskCreate,
    TaskRecord,
    TaskState,
    freeze_command_working_directory,
)
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
        working_root: Path | None = None,
    ) -> None:
        self.root, self.store, self.executor = root, store, executor
        self.working_root = (working_root or root).resolve()
        self.max_concurrency = max_concurrency
        self._scheduler: asyncio.Task[None] | None = None
        self._starters: dict[str, asyncio.Task[None]] = {}
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
        self._queue_cursor: tuple[str, str] | None = None

    def submit(self, draft: TaskCreate) -> TaskRecord:
        draft = self._prepare_draft(draft)
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
        drafts = [self._prepare_draft(draft) for draft in drafts]
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
        logger.info(
            "batch queued batch_id=%s tasks=%s template=%s", batch_id, len(records), template
        )
        self._wake.set()
        return batch_id, records

    def _prepare_draft(self, draft: TaskCreate) -> TaskCreate:
        """Freeze a controller-root-relative cwd as an absolute task snapshot."""
        working_directory = Path(draft.working_directory)
        if not working_directory.is_absolute():
            working_directory = self.working_root / working_directory
        frozen_directory = str(working_directory.resolve())
        return draft.model_copy(
            update={
                "working_directory": frozen_directory,
                "command": freeze_command_working_directory(draft.command, frozen_directory),
            }
        )

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
        starters = list(self._starters.values())
        if starters:
            await asyncio.gather(*starters, return_exceptions=True)
        observers = [*self._waiters.values(), *self._interrupts.values()]
        for observer in observers:
            observer.cancel()
        if observers:
            await asyncio.gather(*observers, return_exceptions=True)

    async def shutdown_all(self, timeout_seconds: float = 60) -> None:
        """Stop every queued/running task and verify that no process tree remains."""
        # Close the launch side of the lifecycle before taking the shutdown
        # snapshot.  A task already handed to systemd-run must finish that
        # ownership transfer before cleanup starts; otherwise its unit could
        # appear after the final cgroup check.
        self._stopping = True
        self._wake.set()
        if self._scheduler:
            await self._scheduler
        starters = list(self._starters.values())
        if starters:
            await asyncio.gather(*starters, return_exceptions=True)
        active_states = [
            TaskState.QUEUED,
            TaskState.STARTING,
            TaskState.RUNNING,
            TaskState.STOPPING,
        ]
        # Drain in pages. A controller can have substantially more queued
        # records than running slots, and shutdown must not strand records
        # beyond the first storage page.
        interruptible_states = [TaskState.QUEUED, TaskState.STARTING, TaskState.RUNNING]
        while True:
            batch = self.store.list_tasks(
                states=interruptible_states, limit=10_000, ascending=True
            )
            if not batch:
                break
            for task in batch:
                await self.interrupt(task.id)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = self.store.list_tasks(states=active_states, limit=10_000, ascending=True)
            if not remaining:
                return
            await asyncio.sleep(0.1)
        remaining = self.store.list_tasks(states=active_states, limit=10_000, ascending=True)
        forced_sequences = []
        for task in remaining:
            sequence = self._interrupts.get(task.id)
            if sequence is not None:
                sequence.cancel()
                forced_sequences.append(sequence)
        if forced_sequences:
            await asyncio.gather(*forced_sequences, return_exceptions=True)
        for task in remaining:
            logger.warning("shutdown force cleanup task_id=%s", task.id)
            self.store.transition(
                task.id,
                [TaskState.STARTING, TaskState.RUNNING, TaskState.STOPPING],
                TaskState.STOPPING,
                interrupt_stage="sigkill",
            )
            await self.executor.interrupt(task.id, "sigkill")
        for task in remaining:
            await self._confirm_forced_exit(task.id)

    async def recover(self) -> None:
        for task in self.store.list_tasks(
            states=["starting", "running", "stopping"],
            # Recovery follows persisted ownership, not today's configured
            # capacity. A host may restart after max_concurrency was lowered.
            limit=10_000,
            ascending=True,
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
        active = self.store.list_tasks(
            states=["starting", "running", "stopping"],
            limit=max(self.max_concurrency, 500),
        )
        capacity = max(0, self.max_concurrency - len(active))
        holders: dict[str, list[str]] = {}
        for task in active:
            for key in task.mutex_keys:
                holders.setdefault(key, []).append(task.id)
        held = set(holders)
        if not capacity:
            return
        scan_limit = min(10_000, max(500, capacity * 4))
        queued = self.store.list_tasks(
            states=["queued"],
            limit=scan_limit,
            after=self._queue_cursor,
            ascending=True,
        )
        if not queued and self._queue_cursor is not None:
            self._queue_cursor = None
            queued = self.store.list_tasks(
                states=["queued"], limit=scan_limit, ascending=True
            )
        last_scanned: TaskRecord | None = None
        scanned_all = True
        for task in queued:
            if not capacity:
                scanned_all = False
                break
            last_scanned = task
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
                starter = asyncio.create_task(self._start(task.id), name=f"task-start-{task.id}")
                self._starters[task.id] = starter
                starter.add_done_callback(
                    lambda _finished, task_id=task.id: self._starters.pop(task_id, None)
                )
                capacity -= 1
        if last_scanned is not None:
            self._queue_cursor = (last_scanned.created_at.isoformat(), last_scanned.id)
        if scanned_all and len(queued) < scan_limit:
            self._queue_cursor = None

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
            failures = 0
            while True:
                try:
                    code = await self.executor.wait(task_id)
                    break
                except Exception as exc:
                    failures += 1
                    logger.error(
                        "task result could not be collected; checking ownership "
                        "task_id=%s attempt=%s",
                        task_id,
                        failures,
                    )
                    logger.debug("task wait exception task_id=%s", task_id, exc_info=True)
                    self.store.append_event(
                        task_id,
                        "task.wait_error",
                        {"attempt": failures, "error": str(exc)},
                    )
                    current = self.store.get_task(task_id)
                    try:
                        running = await self.executor.is_running(current)
                        completed = await self.executor.completed_code(task_id)
                    except Exception as probe_exc:
                        self.store.append_event(
                            task_id,
                            "task.wait_probe_error",
                            {"attempt": failures, "error": str(probe_exc)},
                        )
                        running, completed = True, None
                    if completed is not None and not running:
                        code = completed
                        break
                    if not running:
                        self.store.transition(
                            task_id,
                            [TaskState.RUNNING, TaskState.STARTING, TaskState.STOPPING],
                            TaskState.LOST,
                            ended_at=_now(),
                            elapsed_seconds=_elapsed(current),
                        )
                        self._terminal()
                        return
                    self.store.append_event(
                        task_id,
                        "task.wait_retry",
                        {"attempt": failures, "process_tree_running": True},
                    )
                    await asyncio.sleep(min(0.25 * failures, 2.0))
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
        finally:
            self._waiters.pop(task_id, None)
            self._wake.set()

    def _evaluate_result(self, task: TaskRecord, code: int):
        if task.interrupt_stage or not self._result_evaluator:
            return None, task.custom
        try:
            evaluated = self._result_evaluator(
                task.model_copy(update={"exit_code": code}),
                {"root": str(self.working_root)},
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
        now = time.monotonic()
        deadline = now + timeout_seconds
        elapsed_in_apply = max(0.0, action.timeout_seconds - timeout_seconds)
        hard_deadline = (
            now + max(0.0, action.max_timeout_seconds - elapsed_in_apply)
            if action.max_timeout_seconds is not None
            else deadline
        )
        needle = action.output_contains.encode() if action.output_contains else None
        tail = b""
        advance.clear()
        while time.monotonic() < min(deadline, hard_deadline):
            if self.store.get_task(task_id).state in TERMINAL_STATES:
                return
            if advance.is_set():
                advance.clear()
                return
            if needle or action.extend_timeout_on_output:
                chunk, offset = self.read_log(task_id, offset, 65536)
                if chunk:
                    if action.extend_timeout_on_output:
                        deadline = min(
                            time.monotonic() + action.timeout_seconds,
                            hard_deadline,
                        )
                    if needle:
                        tail = (tail + chunk)[-max(len(needle) * 2, 1024) :]
                        if needle in tail:
                            return
            await asyncio.sleep(0.05)

    async def _confirm_forced_exit(self, task_id: str) -> None:
        """Keep ownership until the real process tree is gone; never report a guessed exit."""
        attempt = 0
        while True:
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

    def search_log(
        self,
        task_id: str,
        query: str,
        *,
        case_sensitive: bool = False,
        whole_word: bool = False,
        regex: bool = False,
        max_results: int = 200,
        timeout_seconds: float = 14.0,
    ) -> dict[str, object]:
        self.store.get_task(task_id)
        if not query:
            return {"items": [], "truncated": False}
        expression = query if regex else re.escape(query)
        if whole_word:
            expression = rf"\b(?:{expression})\b"
        pattern = re.compile(expression, 0 if case_sensitive else re.IGNORECASE)
        path = self.root / "logs" / task_id / "output.log"
        if not path.exists():
            return {"items": [], "truncated": False}
        items: list[dict[str, object]] = []
        overlap = b""
        absolute = 0
        lines_seen = 0
        deadline = time.monotonic() + timeout_seconds
        with path.open("rb") as stream:
            while raw := stream.read(1024 * 1024):
                if time.monotonic() >= deadline:
                    raise TimeoutError("log search timed out")
                combined = overlap + raw
                text = combined.decode("utf-8", errors="replace")
                overlap_lines = overlap.count(b"\n")
                for match in pattern.finditer(text):
                    before = text[: match.start()]
                    through = text[: match.end()]
                    relative = len(before.encode("utf-8", errors="replace")) - len(overlap)
                    relative_end = len(through.encode("utf-8", errors="replace")) - len(overlap)
                    # A hit wholly inside the overlap was already reported. A hit
                    # crossing the block boundary belongs to this block and must
                    # not be discarded.
                    if relative_end <= 0:
                        continue
                    if len(items) >= max_results:
                        return {"items": items, "truncated": True}
                    left = max(text.rfind("\n", 0, match.start()) + 1, match.start() - 160)
                    right_break = text.find("\n", match.end())
                    right = min(
                        len(text) if right_break < 0 else right_break,
                        match.end() + 240,
                    )
                    items.append(
                        {
                            "offset": max(0, absolute + relative),
                            "line": lines_seen - overlap_lines + before.count("\n") + 1,
                            "preview": text[left:right].rstrip("\r")[:400],
                        }
                    )
                lines_seen += raw.count(b"\n")
                absolute += len(raw)
                overlap = combined[-4096:]
        return {"items": items, "truncated": False}

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
