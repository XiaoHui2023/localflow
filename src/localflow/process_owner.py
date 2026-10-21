"""Linux task-family owner for installations without a systemd user manager.

The owner survives the command leader, adopts double-forked children, and only
returns the leader's status after every descendant has been reaped.
"""
from __future__ import annotations

import ctypes
import errno
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def _descendants(pid: int) -> set[int]:
    found: set[int] = set()
    pending = [pid]
    while pending:
        parent = pending.pop()
        # A child can be created by any thread, not just the thread-group leader.
        for entry in Path(f"/proc/{parent}/task").glob("*/children"):
            try:
                children = {int(value) for value in entry.read_text().split()}
            except (OSError, ValueError):
                continue
            pending.extend(children - found)
            found.update(children)
    return found


def _signal_family(sig: int) -> None:
    for pid in _descendants(os.getpid()):
        try:
            # Pin the process identity before delivering either signal.
            opener = getattr(os, "pidfd_open", None)
            sender = getattr(signal, "pidfd_send_signal", None)
            if opener is None or sender is None:
                raise OSError(errno.ENOSYS, "pidfd unavailable in this Python build")
            descriptor = opener(pid)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                continue
            if exc.errno not in (errno.ENOSYS, errno.EINVAL):
                raise
            # Older Ubuntu kernels have subreapers but no pidfds. Only direct
            # children are safe to signal by PID: they cannot be reused before
            # this owner reaps them. Further descendants are adopted on exit.
            direct = Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children")
            if pid in {int(value) for value in direct.read_text().split()}:
                try:
                    os.kill(pid, sig)
                    if sig != signal.SIGKILL:
                        os.kill(pid, signal.SIGCONT)
                except ProcessLookupError:
                    pass
            continue
        try:
            sender(descriptor, sig)
            if sig != signal.SIGKILL:
                sender(descriptor, signal.SIGCONT)
        except ProcessLookupError:
            pass
        finally:
            os.close(descriptor)


def own(command: list[str], directory: Path) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot establish task-family ownership")
    control = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    control.bind(str(directory / "control"))
    os.chmod(directory / "control", 0o600)
    control.settimeout(0.05)
    environment = os.environ.copy()
    for key in ("LOCALFLOW_INTERNAL_MODE", "LOCALFLOW_PROCESS_OWNER"):
        environment.pop(key, None)
    try:
        primary = subprocess.Popen(command, env=environment, start_new_session=True)
    except OSError as exc:
        (directory / "ready.tmp").write_text(json.dumps({"error": str(exc)}))
        (directory / "ready.tmp").replace(directory / "ready")
        control.close()
        return 127
    # External controller signals must not kill the owner before it reaps children.
    requested = 0

    def request(sig: int, _frame: object) -> None:
        nonlocal requested
        requested = sig

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, request)
    status: int | None = None
    force = False
    drained = False
    try:
        (directory / "ready.tmp").write_text(json.dumps({"pid": primary.pid, "owner": os.getpid()}))
        (directory / "ready.tmp").replace(directory / "ready")
        while True:
            try:
                while True:
                    pid, child_status = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break
                    if pid == primary.pid:
                        status = os.waitstatus_to_exitcode(child_status)
                        primary.returncode = status
            except ChildProcessError:
                drained = True
                break
            try:
                message = control.recv(32)
                requested = {b"sigint": signal.SIGINT, b"sigterm": signal.SIGTERM,
                             b"sigkill": signal.SIGKILL}.get(message, requested)
            except TimeoutError:
                pass
            if requested:
                force = force or requested == signal.SIGKILL
                _signal_family(requested)
                requested = 0
            if force:
                # Re-scan after adoption/forks until the kernel reports ECHILD.
                _signal_family(signal.SIGKILL)
    finally:
        if not drained:
            # Failure after spawning still owns the acquired family. Do not
            # abandon children on an output/receipt/control-channel exception.
            while True:
                _signal_family(signal.SIGKILL)
                try:
                    while os.waitpid(-1, os.WNOHANG)[0]:
                        pass
                except ChildProcessError:
                    break
                time.sleep(0.02)
        control.close()
    code = status if status is not None else 127
    if code < 0:
        if -code != signal.SIGKILL:
            signal.signal(-code, signal.SIG_DFL)
        os.kill(os.getpid(), -code)
    return code


def main() -> None:
    raise SystemExit(own(sys.argv[1:], Path(os.environ["LOCALFLOW_PROCESS_OWNER"])))


if __name__ == "__main__":
    main()
