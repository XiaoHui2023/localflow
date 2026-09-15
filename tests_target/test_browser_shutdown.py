from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from localflow.paths import initialize_state_root
from localflow.settings import initialize_config_root


@pytest.mark.skipif(os.name != "nt", reason="the local gate targets installed Microsoft Edge")
def test_real_edge_page_does_not_hold_controller_shutdown(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    frontend = repository / "frontend"
    npx = shutil.which("npx")
    if shutil.which("node") is None or npx is None:
        pytest.skip("Node.js and npx are required")
    workspace = tmp_path / "workspace"
    state = tmp_path / "state"
    initialize_config_root(workspace)
    initialize_state_root(state)
    config_path = workspace / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config.setdefault("server", {}).update({"bind": "127.0.0.1", "port": 0})
    config.setdefault("execution", {})["backend"] = "subprocess"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    log_path = tmp_path / "controller.log"
    with log_path.open("wb") as log:
        controller = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "localflow.cli",
                "--workspace",
                str(workspace),
                "--data",
                str(state),
            ],
            cwd=repository,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    try:
        port_file = state / "runtime" / "port"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not port_file.is_file():
            if controller.poll() is not None:
                pytest.fail(log_path.read_text(encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        assert port_file.is_file(), log_path.read_text(encoding="utf-8", errors="replace")
        url = port_file.read_text(encoding="ascii").strip()
        environment = {
            **os.environ,
            "LOCALFLOW_QA_URL": url,
            "LOCALFLOW_QA_ROOT": str(workspace),
        }
        browser = subprocess.run(
            [npx, "playwright", "test", "--project=edge-live-shutdown"],
            cwd=frontend,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        assert browser.returncode == 0, browser.stdout + browser.stderr
        assert controller.wait(timeout=3) == 0, log_path.read_text(
            encoding="utf-8", errors="replace"
        )
        assert not port_file.exists()
        assert not (state / "runtime" / "localflow.pid").exists()
    finally:
        if controller.poll() is None:
            controller.kill()
            controller.wait(timeout=5)
