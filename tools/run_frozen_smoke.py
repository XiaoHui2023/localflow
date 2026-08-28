#!/usr/bin/env python3
"""对冻结产物执行跨目录、无源码依赖的代表性任务闭环。"""

from __future__ import annotations

import argparse
import base64
import http.cookiejar
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from pathlib import Path


def request(opener, url: str, method: str = "GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with opener.open(req, timeout=5) as response:
        return response.status, response.read()


def wait_for(predicate, timeout: float, message: str):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (OSError, urllib.error.URLError, ValueError) as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"{message}; last error: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"binary not found: {binary}")

    with tempfile.TemporaryDirectory(prefix="localflow-frozen-") as folder:
        isolated = Path(folder)
        if args.bundle_root is None:
            root = isolated / "bundle"
            root.mkdir()
            copied_binary = root / binary.name
            shutil.copy2(binary, copied_binary)
            copied_binary.chmod(0o755)
            binary = copied_binary
        else:
            root = args.bundle_root.resolve()
            if binary.parent != root:
                raise SystemExit("--binary must be directly inside --bundle-root")
        clean_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME", "LOCALFLOW_WEB_DIST"}
        }
        probe = subprocess.run(
            [binary],
            cwd=isolated,
            env={**clean_env, "LOCALFLOW_STARTUP_PROBE": "1"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        endpoints = re.findall(r"https?://[^\s]+", probe.stdout)
        if probe.returncode != 0 or not endpoints:
            raise RuntimeError(
                "frozen executable did not print its startup endpoint:\n"
                f"{probe.stdout}{probe.stderr}"
            )
        startup_host = urllib.parse.urlsplit(endpoints[-1]).hostname
        try:
            startup_address = ipaddress.ip_address(startup_host or "")
        except ValueError as exc:
            raise RuntimeError(f"invalid startup endpoint: {endpoints[-1]}") from exc
        if (
            startup_address.is_loopback
            or startup_address.is_unspecified
            or not startup_address.is_private
        ):
            raise RuntimeError(
                f"startup endpoint is not a copyable private LAN address: {endpoints[-1]}"
            )
        config = root / "config.yaml"
        config.write_text(
            "server:\n  bind: 127.0.0.1\n  port: 0\n"
            "execution:\n  backend: subprocess\n  max_concurrency: 2\n",
            encoding="utf-8",
        )

        rejected = subprocess.run(
            [binary, "--help"],
            cwd=isolated,
            env=clean_env,
            capture_output=True,
            text=True,
        )
        if rejected.returncode == 0 or "does not accept arguments" not in rejected.stderr:
            raise RuntimeError("frozen executable still exposes command-line arguments")

        log_path = isolated / "server.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [binary],
                cwd=isolated,
                env=clean_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        stopped_explicitly = False
        try:
            endpoint = wait_for(
                lambda: (
                    (root / "runtime" / "port").read_text(encoding="ascii").strip()
                    if (root / "runtime" / "port").is_file()
                    else None
                ),
                30,
                "server did not publish its endpoint",
            )
            cookies = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
            status, page = request(opener, endpoint + "/")
            if status != 200 or b'<div id="root">' not in page:
                raise RuntimeError("embedded frontend was not served")

            key = (root / "secrets" / "web-admin-key").read_text(
                encoding="ascii"
            ).strip()
            _, login_body = request(
                opener, endpoint + "/api/v1/auth/local-sessions", "POST", {"key": key}
            )
            csrf = json.loads(login_body)["csrf_token"]
            headers = {"Origin": endpoint, "X-CSRF-Token": csrf}
            payload = {
                "name": "frozen-release-smoke",
                "labels": ["release", "frozen"],
                "working_directory": str(isolated),
                "command": ["/bin/sh", "-lc", "printf 'LOCALFLOW_FROZEN_OK\\n'"],
                "mutex_keys": ["release-smoke"],
                "custom": {"artifact": binary.name},
            }
            _, task_body = request(opener, endpoint + "/api/v1/tasks", "POST", payload, headers)
            task_id = json.loads(task_body)["task_id"]

            def completed():
                _, value = request(opener, endpoint + f"/api/v1/tasks/{task_id}")
                task = json.loads(value)
                if task["state"] in {"failed", "cancelled", "lost"}:
                    raise RuntimeError(f"frozen smoke task ended as {task['state']}")
                return task if task["state"] == "succeeded" else None

            wait_for(completed, 30, "frozen smoke task did not succeed")
            _, log_body = request(opener, endpoint + f"/api/v1/tasks/{task_id}/logs")
            output = base64.b64decode(json.loads(log_body)["data"])
            if b"LOCALFLOW_FROZEN_OK" not in output:
                raise RuntimeError("task output marker is missing")
            pid_file = root / "runtime" / "localflow.pid"
            controller_pid = int(pid_file.read_text(encoding="ascii").strip())
            for protected_signal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                os.killpg(process.pid, protected_signal)
                time.sleep(0.2)
                try:
                    os.kill(controller_pid, 0)
                except ProcessLookupError as exc:
                    raise RuntimeError(
                        f"controller exited on protected signal {protected_signal}"
                    ) from exc
                status, _ = request(opener, endpoint + "/api/v1/system/status")
                if status != 200:
                    raise RuntimeError(
                        f"controller stopped serving after protected signal {protected_signal}"
                    )
            child_pid_file = isolated / "protected-child.pid"
            long_payload = {
                "name": "shutdown-cleanup-smoke",
                "labels": ["release", "shutdown"],
                "working_directory": str(isolated),
                "command": [
                    "/bin/sh",
                    "-lc",
                    "trap '' INT TERM; echo $$ > protected-child.pid; while :; do sleep 1; done",
                ],
                "stop": {
                    "actions": [
                        {"type": "signal", "signal": "SIGINT", "timeout_seconds": 0.2},
                        {"type": "signal", "signal": "SIGTERM", "timeout_seconds": 0.2},
                    ]
                },
            }
            request(opener, endpoint + "/api/v1/tasks", "POST", long_payload, headers)
            child_pid = int(
                wait_for(
                    lambda: child_pid_file.read_text(encoding="ascii").strip()
                    if child_pid_file.is_file()
                    else None,
                    30,
                    "protected child did not start",
                )
            )
            os.kill(controller_pid, signal.SIGUSR1)
            wait_for(
                lambda: not Path(f"/proc/{controller_pid}").exists(),
                90,
                "controller PID remained after explicit shutdown",
            )
            if process.poll() is None:
                process.wait(timeout=5)
            stopped_explicitly = True
            if process.returncode not in {0, -signal.SIGHUP}:
                raise RuntimeError(f"onefile wrapper returned {process.returncode}")
            if Path(f"/proc/{child_pid}").exists():
                raise RuntimeError(f"task process remained after controller shutdown: {child_pid}")
            if pid_file.exists():
                raise RuntimeError("controller PID file remained after shutdown")
            print(f"frozen release smoke passed: {binary} task={task_id} cleanup_pid={child_pid}")
        finally:
            if not stopped_explicitly:
                pid_file = root / "runtime" / "localflow.pid"
                if pid_file.is_file():
                    with suppress(ProcessLookupError, ValueError):
                        os.kill(
                            int(pid_file.read_text(encoding="ascii").strip()), signal.SIGUSR1
                        )
                else:
                    process.kill()
                if process.poll() is None:
                    try:
                        process.wait(timeout=90)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            if process.returncode not in {0, -signal.SIGHUP}:
                print(log_path.read_text(encoding="utf-8", errors="replace"))
                raise RuntimeError(f"server exited with {process.returncode}")


if __name__ == "__main__":
    main()
