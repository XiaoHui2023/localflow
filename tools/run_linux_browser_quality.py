#!/usr/bin/env python3
"""Run Chrome and Firefox against the final Linux release executable."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
LEGACY_BROWSERS = (
    ("chrome-84", "selenium/standalone-chrome:84.0", "chrome"),
    ("firefox-78", "selenium/standalone-firefox:78.0", "firefox"),
)


def wait_for_endpoint(root: Path, process: subprocess.Popen[bytes]) -> str:
    port_file = root / "runtime" / "port"
    deadline = time.monotonic() + 30
    error = "endpoint file was not created"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"release executable exited with {process.returncode}")
        if port_file.is_file():
            endpoint = port_file.read_text(encoding="ascii").strip()
            try:
                with urllib.request.urlopen(endpoint, timeout=1) as response:
                    if response.status == 200:
                        return endpoint
            except OSError as exc:
                error = str(exc)
        time.sleep(0.1)
    raise RuntimeError(f"release web endpoint did not become ready: {error}")


def pull_image(docker: str, image: str) -> None:
    for attempt in range(3):
        try:
            result = subprocess.run([docker, "pull", image], check=False, timeout=300)
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and result.returncode == 0:
            return
        if attempt < 2:
            time.sleep(2**attempt)
    raise RuntimeError(f"could not pull legacy browser image after 3 attempts: {image}")


def wait_for_selenium(endpoint: str) -> None:
    deadline = time.monotonic() + 30
    error = "Selenium did not answer"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{endpoint}/status", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError as exc:
            error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"legacy browser did not become ready: {error}")


def run_legacy_browser(
    *, docker: str, npm: str, image: str, browser: str, project: str, environment: dict[str, str]
) -> int:
    name = f"localflow-{project}-{os.getpid()}"
    pull_image(docker, image)
    subprocess.run(
        [docker, "run", "--rm", "-d", "-p", "127.0.0.1::4444", "--shm-size=2g", "--name", name, image],
        check=True,
    )
    try:
        mapping = subprocess.run(
            [docker, "port", name, "4444/tcp"], check=True, capture_output=True, text=True
        ).stdout.strip()
        selenium = f"http://{mapping}/wd/hub"
        wait_for_selenium(selenium)
        legacy_environment = {
            **environment,
            "LOCALFLOW_LEGACY_BROWSER": browser,
            "LOCALFLOW_LEGACY_PROJECT": project,
            "LOCALFLOW_SELENIUM_URL": selenium,
        }
        return subprocess.run(
            [npm, "run", "test:legacy-compat"],
            cwd=REPOSITORY / "frontend",
            env=legacy_environment,
            check=False,
        ).returncode
    finally:
        subprocess.run([docker, "rm", "-f", name], check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    source = args.binary.resolve()
    if not source.is_file():
        raise SystemExit(f"binary not found: {source}")
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm is required")
    docker = shutil.which("docker")
    if not docker:
        raise SystemExit("docker is required for fixed-version browser testing")

    with tempfile.TemporaryDirectory(prefix="localflow-linux-browser-") as folder:
        root = Path(folder) / "release"
        root.mkdir()
        binary = root / "localflow"
        shutil.copy2(source, binary)
        binary.chmod(0o755)
        config = root / "config.yaml"
        config.write_text(
            "server:\n  bind: 0.0.0.0\n  port: 0\n  anonymous_access: summary\n"
            "execution:\n  backend: subprocess\n  max_concurrency: 1\n"
            "  sigint_grace_seconds: 0.2\n  sigterm_grace_seconds: 0.2\n",
            encoding="utf-8",
        )
        log_path = Path(folder) / "localflow.log"
        clean_environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME", "LOCALFLOW_WEB_DIST"}
        }
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [binary],
                cwd=folder,
                env=clean_environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        try:
            endpoint = wait_for_endpoint(root, process)
            admin_key = (root / "secrets" / "web-admin-key").read_text(
                encoding="ascii"
            ).strip()
            evidence = REPOSITORY / "quality" / "evidence" / "browser-linux"
            environment = {
                **clean_environment,
                "LOCALFLOW_QA_URL": endpoint,
                "LOCALFLOW_QA_ROOT": str(root),
                "LOCALFLOW_QA_PYTHON": "/usr/bin/python3",
                "LOCALFLOW_QA_ADMIN_KEY": admin_key,
                "LOCALFLOW_COMPAT_EVIDENCE": str(evidence),
            }
            current = subprocess.run(
                [npm, "run", "test:linux-compat"],
                cwd=REPOSITORY / "frontend",
                env=environment,
                check=False,
            ).returncode
            if current:
                return current
            for project, image, browser in LEGACY_BROWSERS:
                result = run_legacy_browser(
                    docker=docker,
                    npm=npm,
                    image=image,
                    browser=browser,
                    project=project,
                    environment=environment,
                )
                if result:
                    return result
            return 0
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGUSR1)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
            if process.returncode not in {0, -signal.SIGINT}:
                print(log_path.read_text(encoding="utf-8", errors="replace"))
                raise RuntimeError(f"release server exited with {process.returncode}")


if __name__ == "__main__":
    raise SystemExit(main())
