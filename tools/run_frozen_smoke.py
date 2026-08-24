#!/usr/bin/env python3
"""对冻结产物执行跨目录、无源码依赖的代表性任务闭环。"""

from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
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
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"binary not found: {binary}")

    with tempfile.TemporaryDirectory(prefix="localflow-frozen-") as folder:
        isolated = Path(folder)
        root = isolated / "runtime-root"
        clean_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME", "LOCALFLOW_WEB_DIST"}
        }
        subprocess.run([binary, "init", "--root", root], cwd=isolated, env=clean_env, check=True)
        config = root / "config" / "server.yaml"
        text = config.read_text(encoding="utf-8").replace("backend: systemd", "backend: subprocess")
        config.write_text(text, encoding="utf-8")

        log_path = isolated / "server.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [binary, "serve", "--root", root],
                cwd=isolated,
                env=clean_env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
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

            code = subprocess.check_output(
                [binary, "login-code", "--root", root],
                cwd=isolated,
                env=clean_env,
                text=True,
            ).strip()
            _, login_body = request(
                opener, endpoint + "/api/v1/auth/local-sessions", "POST", {"code": code}
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
            print(f"frozen release smoke passed: {binary} task={task_id}")
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
            if process.returncode not in {0, -signal.SIGINT}:
                print(log_path.read_text(encoding="utf-8", errors="replace"))
                raise RuntimeError(f"server exited with {process.returncode}")


if __name__ == "__main__":
    main()
