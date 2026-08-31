from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import selectors
import shlex
import signal
import socket
import struct
import termios
from contextlib import suppress
from pathlib import Path

from .control import control_socket_path
from .log_files import BoundedLogWriter, lifecycle_line


def supervise(root: Path, task_id: str) -> int:
    task = json.loads(
        (root / "runtime" / "instances" / f"{task_id}.json").read_text(encoding="utf-8")
    )
    log_path = root / "logs" / task_id / "output.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    limits = task.get("_localflow", {})
    child_pid, master = pty.fork()
    if child_pid == 0:
        os.chdir(task["working_directory"])
        os.execvp(task["command"][0], task["command"])

    def forward(signum: int, _frame: object) -> None:
        with suppress(ProcessLookupError):
            os.killpg(child_pid, signum)

    for handled_signal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(handled_signal, forward)
    selector = selectors.DefaultSelector()
    selector.register(master, selectors.EVENT_READ)
    control_path = control_socket_path(root, task_id)
    control_path.unlink(missing_ok=True)
    control = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    control.bind(str(control_path))
    os.chmod(control_path, 0o600)
    control.setblocking(False)
    selector.register(control, selectors.EVENT_READ)
    with BoundedLogWriter(
        log_path,
        int(limits.get("task_log_max_bytes", 100 * 1024 * 1024)),
        int(limits.get("keep_free_bytes", 0)),
    ) as log:
        shown_command = task["command"][2] if task["command"][:2] == ["/bin/sh", "-lc"] else shlex.join(task["command"])
        log.write(lifecycle_line("process.command", cwd=task["working_directory"], command=shown_command))
        log.write(lifecycle_line("process.started", pid=child_pid, terminal="pty"))
        while True:
            for key, _ in selector.select(0.25):
                if key.fileobj is control:
                    message = control.recv(65536)
                    if message[:1] == b"I":
                        os.write(master, message[1:])
                    elif message[:1] == b"R":
                        rows, cols = (int(item) for item in message[1:].split(b",", 1))
                        window = struct.pack("HHHH", rows, cols, 0, 0)
                        fcntl.ioctl(master, termios.TIOCSWINSZ, window)
                    continue
                try:
                    chunk = os.read(key.fd, 65536)
                except OSError:
                    chunk = b""
                if chunk:
                    log.write(chunk)
            waited, status = os.waitpid(child_pid, os.WNOHANG)
            if waited:
                code = os.waitstatus_to_exitcode(status)
                log.write(lifecycle_line("process.exited", exit_code=code))
                result = root / "runtime" / "instances" / f"{task_id}.exit"
                result.write_text(str(code), encoding="ascii")
                os.chmod(result, 0o600)
                control.close()
                control_path.unlink(missing_ok=True)
                return code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    raise SystemExit(supervise(args.root.resolve(), args.task))


if __name__ == "__main__":
    main()
