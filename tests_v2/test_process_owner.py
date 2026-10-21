"""Linux integration checks use actual children and independent kernel identity."""
from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from localflow.executor import SubprocessExecutor
from localflow.models import StopAction, TaskCreate
from localflow.service import TaskService
from localflow.settings import initialize_root
from localflow.storage import Store

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux task-family owner")


def task(directory: Path, command: list[str], identifier: str = "owner-test"):
    return SimpleNamespace(id=identifier, command=command, working_directory=str(directory), custom={})


async def until(check) -> None:
    async with asyncio.timeout(8):
        while not check():
            await asyncio.sleep(0.02)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [0, 7])
async def test_primary_exit_and_stdin_output_preserved(tmp_path: Path, code: int) -> None:
    executor = SubprocessExecutor()
    item = task(tmp_path, [sys.executable, "-c",
                          f"import sys; print(input(),flush=True); sys.exit({code})"])
    log = tmp_path / "output.log"
    await executor.start(item, log)
    await executor.write(item.id, b"input preserved\n")
    assert await asyncio.wait_for(executor.wait(item.id), 8) == code
    assert b"input preserved" in log.read_bytes()
    assert not executor._owners


@pytest.mark.asyncio
@pytest.mark.parametrize("stage,expected", [("sigterm", -15), ("sigkill", -9)])
async def test_primary_signal_status_preserved(tmp_path: Path, stage: str, expected: int) -> None:
    executor = SubprocessExecutor()
    item = task(tmp_path, [sys.executable, "-c", "import time; time.sleep(120)"])
    await executor.start(item, tmp_path / "output.log")
    await executor.interrupt(item.id, stage)
    assert await asyncio.wait_for(executor.wait(item.id), 8) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("detached", [False, True])
@pytest.mark.parametrize("stopped", [False, True])
async def test_parent_exit_does_not_release_live_family(
    tmp_path: Path, detached: bool, stopped: bool,
) -> None:
    marker = tmp_path / "child.pid"
    child = ("import os,signal,time; from pathlib import Path; "
             "signal.signal(signal.SIGINT,signal.SIG_IGN); "
             "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
             f"Path({str(marker)!r}).write_text(str(os.getpid())); "
             + ("os.kill(os.getpid(),signal.SIGSTOP); " if stopped else "")
             + "time.sleep(120)")
    command = [sys.executable, "-c", "import subprocess,time; "
               f"subprocess.Popen([{sys.executable!r},'-c',{child!r}],"
               f"start_new_session={detached}); time.sleep(0.3)"]
    executor = SubprocessExecutor()
    item = task(tmp_path, command)
    sibling = task(tmp_path, [sys.executable, "-c", "import time; time.sleep(120)"], "sibling")
    await executor.start(item, tmp_path / "output.log")
    await executor.start(sibling, tmp_path / "sibling.log")
    pid = None
    try:
        await until(marker.exists)
        pid = int(marker.read_text())
        await asyncio.sleep(0.5)
        assert await executor.is_running(item)
        assert await executor.completed_code(item.id) is None
        observer = asyncio.create_task(executor.wait(item.id))
        await asyncio.sleep(0.05)
        observer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await observer
        assert await executor.is_running(item)
        for stage in ("sigint", "sigterm", "sigkill"):
            await executor.interrupt(item.id, stage)
            await asyncio.sleep(0.1)
        assert await asyncio.wait_for(executor.wait(item.id), 8) == 0
        # /proc absence proves reaping, including zombies (not only kill(pid, 0)).
        assert not Path(f"/proc/{pid}").exists()
        assert await executor.is_running(sibling)
    finally:
        for current in (item, sibling):
            if current.id in executor._processes:
                await executor.interrupt(current.id, "sigkill")
                await asyncio.wait_for(executor.wait(current.id), 8)
        if pid and Path(f"/proc/{pid}").exists():
            os.kill(pid, signal.SIGKILL)


@pytest.mark.asyncio
async def test_missing_command_releases_owner(tmp_path: Path) -> None:
    executor = SubprocessExecutor()
    item = task(tmp_path, [str(tmp_path / "missing-command")])
    with pytest.raises(OSError):
        await executor.start(item, tmp_path / "output.log")
    assert not executor._processes
    assert not executor._owners


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_stop_exec_timeout_and_cancellation_reap_detached_children(
    tmp_path: Path, cancel: bool,
) -> None:
    root = tmp_path / "root"
    initialize_root(root)
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor())
    item = service.submit(TaskCreate(name="stop-helper", working_directory=str(root),
                                     command=[sys.executable, "-c", "pass"]))
    marker = root / "stop-child.pid"
    child = ("import os,time,signal; from pathlib import Path; "
             "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
             f"Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(120)")
    command = [sys.executable, "-c", "import subprocess,time; "
               f"subprocess.Popen([{sys.executable!r},'-c',{child!r}],start_new_session=True); "
               "time.sleep(120)"]
    action = StopAction(type="exec", command=command, timeout_seconds=120 if cancel else 1)
    sequence = asyncio.create_task(service._apply_stop_action(item, action))
    pid = None
    try:
        await until(marker.exists)
        pid = int(marker.read_text())
        if cancel:
            sequence.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(sequence, 8)
        else:
            await asyncio.wait_for(sequence, 8)
        assert not Path(f"/proc/{pid}").exists()
    finally:
        if not sequence.done():
            sequence.cancel()
            await asyncio.gather(sequence, return_exceptions=True)
        if pid and Path(f"/proc/{pid}").exists():
            os.kill(pid, signal.SIGKILL)
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_api", [False, True])
async def test_old_kernel_without_pidfd_reaps_adopted_family(
    tmp_path: Path, missing_api: bool,
) -> None:
    directory = tmp_path / "owner"
    directory.mkdir(mode=0o700)
    marker = tmp_path / "child.pid"
    child = ("import os,time; from pathlib import Path; "
             f"Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(120)")
    command = [sys.executable, "-c", "import subprocess,time; "
               f"subprocess.Popen([{sys.executable!r},'-c',{child!r}],start_new_session=True); "
               "time.sleep(120)"]
    # Exercise the documented old-kernel syscall failure in a dedicated owner,
    # preserving real adoption, signal delivery, identity and reaping behavior.
    runner = ("import os,errno\nfrom localflow.process_owner import main\n"
              "def unavailable(pid):\n raise OSError(errno.ENOSYS, 'old kernel')\n"
              + ("os.pidfd_open=None\n" if missing_api else "os.pidfd_open=unavailable\n")
              + "main()\n")
    process = subprocess.Popen([sys.executable, "-c", runner, *command],
                               env={**os.environ, "LOCALFLOW_PROCESS_OWNER": str(directory)})
    pid = None
    try:
        await until(marker.exists)
        pid = int(marker.read_text())
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
            control.sendto(b"sigkill", str(directory / "control"))
        await until(lambda: process.poll() is not None)
        assert not Path(f"/proc/{pid}").exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        if pid and Path(f"/proc/{pid}").exists():
            os.kill(pid, signal.SIGKILL)
