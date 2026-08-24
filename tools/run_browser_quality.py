from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import yaml

from localflow.settings import initialize_root

REPOSITORY = Path(__file__).resolve().parents[1]


def wait_for_server(root: Path, process: subprocess.Popen[str]) -> str:
    port_file = root / "runtime" / "port"
    deadline = time.monotonic() + 30
    last_error = "port file not written"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"LocalFlow exited before readiness with {process.returncode}")
        if port_file.is_file():
            url = port_file.read_text(encoding="ascii").strip()
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        return url
            except OSError as exc:
                last_error = str(exc)
        time.sleep(0.1)
    raise TimeoutError(f"LocalFlow did not become ready: {last_error}")


def main() -> int:
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is required for the browser quality gate")
    frontend = REPOSITORY / "frontend"
    evidence = REPOSITORY / "quality" / "evidence" / "browser"
    evidence.mkdir(parents=True, exist_ok=True)
    for name in (
        "admin-task-detail.png",
        "admin-template-cases.png",
        "admin-config-monaco.png",
        "admin-mobile-390.png",
        "browser-receipt.json",
    ):
        target = evidence / name
        if target.is_file():
            target.unlink()

    subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    with tempfile.TemporaryDirectory(prefix="localflow-browser-qa-") as temporary:
        root = Path(temporary) / "root"
        initialize_root(root)
        settings_path = root / "config" / "server.yaml"
        settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
        settings["execution"].update(
            {
                "backend": "subprocess",
                "max_concurrency": 1,
                "sigint_grace_seconds": 0.2,
                "sigterm_grace_seconds": 0.2,
            }
        )
        settings_path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
        (root / "qa-cases" / "case-a").mkdir(parents=True)
        (root / "qa-cases" / "case-b").mkdir(parents=True)
        environment = os.environ.copy()
        environment["LOCALFLOW_WEB_DIST"] = str(frontend / "dist")
        process = subprocess.Popen(
            [sys.executable, "-m", "localflow.cli", "serve", "--root", str(root)],
            cwd=REPOSITORY,
            env=environment,
            text=True,
        )
        try:
            url = wait_for_server(root, process)
            login_code = (root / "secrets" / "admin-bootstrap").read_text(
                encoding="ascii"
            ).strip()
            qa_environment = environment.copy()
            qa_environment.update(
                {
                    "LOCALFLOW_QA_URL": url,
                    "LOCALFLOW_QA_ROOT": str(root),
                    "LOCALFLOW_QA_PYTHON": sys.executable,
                    "LOCALFLOW_QA_LOGIN_CODE": login_code,
                }
            )
            result = subprocess.run(
                [npm, "run", "test:e2e"],
                cwd=frontend,
                env=qa_environment,
                check=False,
            )
            return result.returncode
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
