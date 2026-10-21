"""Isolated real-UI refresh and recovery witness; never connects to production."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import yaml

from localflow.settings import initialize_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=30)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output = repo / "quality/evidence/web-connection"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="localflow-web-recovery-") as name:
        root = Path(name)
        initialize_root(root)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        config = root / "config.yaml"
        settings = yaml.safe_load(config.read_text(encoding="utf-8"))
        settings["server"].update(bind="127.0.0.1", port=port, anonymous_access="summary")
        settings["execution"]["backend"] = "subprocess"
        config.write_text(yaml.safe_dump(settings), encoding="utf-8")
        url = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with (output / "server.log").open("wb") as log:

            def start():
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "localflow",
                        "--workspace",
                        str(root),
                        "--data",
                        str(root / ".localflow"),
                    ],
                    cwd=repo,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                for _ in range(300):
                    if process.poll() is not None:
                        raise RuntimeError("isolated server exited; inspect server.log")
                    try:
                        with opener.open(url + "/api/v1/system/status", timeout=1) as response:
                            if response.status == 200:
                                return process
                    except OSError:
                        time.sleep(0.1)
                process.terminate()
                process.wait(timeout=10)
                raise RuntimeError("isolated server readiness timed out")

            server = start()
            browser = None
            restarted = False
            try:
                with (output / "browser.log").open("wb") as browser_log:
                    browser = subprocess.Popen(
                        [
                            "node",
                            str(repo / "frontend/e2e/web-recovery.mjs"),
                            url,
                            str(root),
                            sys.executable,
                            str(output / "verification.json"),
                            str(args.minutes),
                        ],
                        stdout=browser_log,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    deadline = time.monotonic() + args.minutes * 60 + 180
                    while browser.poll() is None and time.monotonic() < deadline:
                        if (root / "restart-request").exists() and not restarted:
                            server.terminate()
                            server.wait(timeout=10)
                            server = start()
                            restarted = True
                            (root / "restart-done").write_text("ready")
                        time.sleep(0.2)
                    if browser.poll() is None:
                        raise RuntimeError("bounded browser verification deadline exceeded")
                    code = browser.returncode
            finally:
                if browser is not None and browser.poll() is None:
                    browser.terminate()
                    browser.wait(timeout=10)
                server.terminate()
                server.wait(timeout=10)
    (output / "lifecycle.json").write_text(
        json.dumps(
            {
                "fixture_removed": not root.exists(),
                "server_restarted": restarted,
                "production_restarted": False,
                "browser_exit": code,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
