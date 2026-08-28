from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .control import control_socket_path
from .log_files import BoundedLogWriter, lifecycle_line
from .models import TaskRecord


def systemd_user_manager_available() -> tuple[bool, str]:
    """Return whether a usable user manager can accept transient units."""

    if os.name == "nt":
        return False, "systemd is unavailable on Windows"
    if not shutil.which("systemd-run") or not shutil.which("systemctl"):
        return False, "systemd-run or systemctl is not installed"
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"systemd user-manager probe failed: {exc}"
    if result.returncode:
        reason = result.stderr.decode(errors="replace").strip()
        return False, reason or "systemd user manager is not reachable"
    return True, "systemd user manager is reachable"


@dataclass(frozen=True)
class StartResult:
    pid: int | None
    reference: str


class Executor(Protocol):
    async def start(self, task: TaskRecord, log_path: Path) -> StartResult: ...
    async def wait(self, task_id: str) -> int: ...
    async def interrupt(self, task_id: str, stage: str) -> bool: ...
    async def is_running(self, task: TaskRecord) -> bool: ...
    async def write(self, task_id: str, data: bytes) -> bool: ...
    async def resize(self, task_id: str, rows: int, cols: int) -> bool: ...
    async def completed_code(self, task_id: str) -> int | None: ...


class SubprocessExecutor:
    """Development executor with process-group signal semantics."""

    def __init__(
        self, task_log_max_bytes: int = 100 * 1024 * 1024, keep_free_bytes: int = 0
    ) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._pumps: dict[str, asyncio.Task[None]] = {}
        self._writers: dict[str, BoundedLogWriter] = {}
        self.task_log_max_bytes = task_log_max_bytes
        self.keep_free_bytes = keep_free_bytes

    async def start(self, task: TaskRecord, log_path: Path) -> StartResult:
        workdir = Path(task.working_directory)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = BoundedLogWriter(log_path, self.task_log_max_bytes, self.keep_free_bytes)
        log.write(lifecycle_line("executor.starting", backend="subprocess"))
        if not workdir.is_dir():
            error = FileNotFoundError(f"working directory does not exist: {workdir}")
            log.write(lifecycle_line("executor.start_failed", error=str(error)))
            log.close()
            raise error
        kwargs: dict[str, object] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            process = await asyncio.create_subprocess_exec(
                *task.command,
                cwd=workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.PIPE,
                **kwargs,
            )
        except BaseException as exc:
            log.write(
                lifecycle_line(
                    "executor.start_failed", error=f"{type(exc).__name__}: {exc}"
                )
            )
            log.close()
            raise
        log.write(lifecycle_line("process.started", pid=process.pid))
        self._processes[task.id] = process
        self._writers[task.id] = log

        async def pump() -> None:
            assert process.stdout is not None
            while chunk := await process.stdout.read(65536):
                log.write(chunk)

        self._pumps[task.id] = asyncio.create_task(pump(), name=f"task-log-{task.id}")
        return StartResult(process.pid, f"process:{process.pid}")

    async def wait(self, task_id: str) -> int:
        process = self._processes[task_id]
        try:
            code = await process.wait()
            pump = self._pumps.get(task_id)
            if pump:
                await pump
            log = self._writers.get(task_id)
            if log:
                log.write(lifecycle_line("process.exited", exit_code=code))
            return code
        finally:
            self._pumps.pop(task_id, None)
            log = self._writers.pop(task_id, None)
            if log:
                log.close()
            self._processes.pop(task_id, None)

    async def interrupt(self, task_id: str, stage: str) -> bool:
        process = self._processes.get(task_id)
        if process is None or process.returncode is not None:
            return False
        if os.name == "nt":
            if stage == "sigint":
                if process.stdin is None:
                    return False
                process.stdin.write(b"\x03")
                await process.stdin.drain()
            elif stage == "sigterm":
                process.terminate()
            else:
                process.kill()
        else:
            sig = {"sigint": signal.SIGINT, "sigterm": signal.SIGTERM, "sigkill": signal.SIGKILL}[
                stage
            ]
            os.killpg(process.pid, sig)
        return True

    async def is_running(self, task: TaskRecord) -> bool:
        process = self._processes.get(task.id)
        return process is not None and process.returncode is None

    async def write(self, task_id: str, data: bytes) -> bool:
        process = self._processes.get(task_id)
        if process is None or process.returncode is not None or process.stdin is None:
            return False
        if data == b"\x03":
            if os.name != "nt":
                return await self.interrupt(task_id, "sigint")
            process.stdin.write(data)
            await process.stdin.drain()
            return True
        if data == b"\x04":
            process.stdin.close()
            return True
        process.stdin.write(data)
        await process.stdin.drain()
        return True

    async def resize(self, task_id: str, rows: int, cols: int) -> bool:
        # The development backend streams pipes rather than a PTY.  Accept a
        # valid resize as a no-op so browser-local fitting does not pollute the
        # task's real output with a misleading protocol error.
        process = self._processes.get(task_id)
        return process is not None and process.returncode is None

    async def completed_code(self, task_id: str) -> int | None:
        process = self._processes.get(task_id)
        return process.returncode if process is not None else None


class SystemdExecutor:
    """Ubuntu executor that gives a transient unit durable process ownership."""

    def __init__(
        self,
        root: Path,
        task_log_max_bytes: int = 100 * 1024 * 1024,
        keep_free_bytes: int = 0,
    ) -> None:
        self.root = root
        self.task_log_max_bytes = task_log_max_bytes
        self.keep_free_bytes = keep_free_bytes

    async def start(self, task: TaskRecord, log_path: Path) -> StartResult:
        unit = f"localflow-task-{task.id}.service"
        descriptor = self.root / "runtime" / "instances" / f"{task.id}.json"
        descriptor.parent.mkdir(parents=True, exist_ok=True)
        payload = task.model_dump(mode="json")
        payload["_localflow"] = {
            "task_log_max_bytes": self.task_log_max_bytes,
            "keep_free_bytes": self.keep_free_bytes,
        }
        descriptor.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(descriptor, 0o600)
        command = [
            "systemd-run",
            "--user",
            "--unit",
            unit,
            "--collect",
            "--quiet",
            "--property",
            f"WorkingDirectory={task.working_directory}",
            "--property",
            "KillMode=control-group",
            "--property",
            "SendSIGKILL=yes",
            "--property",
            "Type=exec",
        ]
        if getattr(sys, "frozen", False):
            executable = os.environ.get("STATICX_PROG_PATH", sys.executable)
            command.extend(
                [
                    "--setenv=LOCALFLOW_INTERNAL_MODE=supervisor",
                    f"--setenv=LOCALFLOW_INTERNAL_ROOT={self.root}",
                    f"--setenv=LOCALFLOW_INTERNAL_TASK={task.id}",
                    executable,
                ]
            )
        else:
            command.extend(
                [
                    sys.executable,
                    "-m",
                    "localflow.supervisor",
                    "--root",
                    str(self.root),
                    "--task",
                    task.id,
                ]
            )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with BoundedLogWriter(
            log_path, self.task_log_max_bytes, self.keep_free_bytes
        ) as log:
            log.write(lifecycle_line("executor.starting", backend="systemd", unit=unit))
            try:
                process = await asyncio.create_subprocess_exec(
                    *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await process.communicate()
                if process.returncode:
                    raise RuntimeError(
                        stderr.decode(errors="replace").strip() or "systemd-run failed"
                    )
            except BaseException as exc:
                log.write(
                    lifecycle_line(
                        "executor.start_failed", error=f"{type(exc).__name__}: {exc}"
                    )
                )
                raise
            log.write(lifecycle_line("executor.accepted", unit=unit))
        return StartResult(None, unit)

    async def wait(self, task_id: str) -> int:
        result = self.root / "runtime" / "instances" / f"{task_id}.exit"
        while True:
            process = await asyncio.create_subprocess_exec(
                "systemctl",
                "--user",
                "is-active",
                "--quiet",
                f"localflow-task-{task_id}.service",
            )
            inactive = await process.wait() != 0
            if result.exists() and inactive:
                return int(result.read_text(encoding="ascii").strip())
            if inactive:
                return 137
            await asyncio.sleep(0.1)

    async def interrupt(self, task_id: str, stage: str) -> bool:
        unit = f"localflow-task-{task_id}.service"
        signal_name = {"sigint": "SIGINT", "sigterm": "SIGTERM", "sigkill": "SIGKILL"}[stage]
        target = "all" if stage == "sigkill" else "main"
        process = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "kill", f"--kill-whom={target}", f"--signal={signal_name}", unit
        )
        return await process.wait() == 0

    async def is_running(self, task: TaskRecord) -> bool:
        if not task.executor_ref:
            return False
        process = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "is-active", "--quiet", task.executor_ref
        )
        return await process.wait() == 0

    async def _control(self, task_id: str, payload: bytes) -> bool:
        path = control_socket_path(self.root, task_id)

        def send() -> bool:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                    client.sendto(payload, str(path))
                return True
            except OSError:
                return False

        return await asyncio.to_thread(send)

    async def write(self, task_id: str, data: bytes) -> bool:
        return await self._control(task_id, b"I" + data)

    async def resize(self, task_id: str, rows: int, cols: int) -> bool:
        return await self._control(task_id, f"R{rows},{cols}".encode("ascii"))

    async def completed_code(self, task_id: str) -> int | None:
        result = self.root / "runtime" / "instances" / f"{task_id}.exit"
        if not result.exists():
            return None
        return int(result.read_text(encoding="ascii").strip())
