from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .control import control_socket_path
from .models import TaskRecord


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

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._logs: dict[str, object] = {}

    async def start(self, task: TaskRecord, log_path: Path) -> StartResult:
        workdir = Path(task.working_directory)
        if not workdir.is_dir():
            raise FileNotFoundError(f"working directory does not exist: {workdir}")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("ab", buffering=0)
        kwargs: dict[str, object] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            process = await asyncio.create_subprocess_exec(
                *task.command,
                cwd=workdir,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.PIPE,
                **kwargs,
            )
        except BaseException:
            log.close()
            raise
        self._processes[task.id] = process
        self._logs[task.id] = log
        return StartResult(process.pid, f"process:{process.pid}")

    async def wait(self, task_id: str) -> int:
        process = self._processes[task_id]
        try:
            return await process.wait()
        finally:
            log = self._logs.pop(task_id, None)
            if log:
                log.close()  # type: ignore[attr-defined]
            self._processes.pop(task_id, None)

    async def interrupt(self, task_id: str, stage: str) -> bool:
        process = self._processes.get(task_id)
        if process is None or process.returncode is not None:
            return False
        if os.name == "nt":
            if stage == "sigint":
                process.send_signal(signal.CTRL_BREAK_EVENT)
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
        process.stdin.write(data)
        await process.stdin.drain()
        return True

    async def resize(self, task_id: str, rows: int, cols: int) -> bool:
        return False

    async def completed_code(self, task_id: str) -> int | None:
        process = self._processes.get(task_id)
        return process.returncode if process is not None else None


class SystemdExecutor:
    """Ubuntu executor that gives a transient unit durable process ownership."""

    def __init__(self, root: Path) -> None:
        self.root = root

    async def start(self, task: TaskRecord, log_path: Path) -> StartResult:
        unit = f"localflow-task-{task.id}.service"
        descriptor = self.root / "runtime" / "instances" / f"{task.id}.json"
        descriptor.parent.mkdir(parents=True, exist_ok=True)
        descriptor.write_text(task.model_dump_json(), encoding="utf-8")
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
            "Type=exec",
            sys.executable,
            "-m",
            "localflow.supervisor",
            "--root",
            str(self.root),
            "--task",
            task.id,
        ]
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode:
            raise RuntimeError(stderr.decode(errors="replace").strip() or "systemd-run failed")
        return StartResult(None, unit)

    async def wait(self, task_id: str) -> int:
        result = self.root / "runtime" / "instances" / f"{task_id}.exit"
        while True:
            if result.exists():
                return int(result.read_text(encoding="ascii").strip())
            process = await asyncio.create_subprocess_exec(
                "systemctl",
                "--user",
                "is-active",
                "--quiet",
                f"localflow-task-{task_id}.service",
            )
            if await process.wait() != 0:
                return 137
            await asyncio.sleep(0.5)

    async def interrupt(self, task_id: str, stage: str) -> bool:
        unit = f"localflow-task-{task_id}.service"
        signal_name = {"sigint": "SIGINT", "sigterm": "SIGTERM", "sigkill": "SIGKILL"}[stage]
        process = await asyncio.create_subprocess_exec(
            "systemctl", "--user", "kill", "--kill-whom=all", f"--signal={signal_name}", unit
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
