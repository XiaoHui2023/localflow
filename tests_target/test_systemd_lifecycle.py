from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("systemctl") is None or os.getpid() == 1,
    reason="requires a test process inside a systemd-based Ubuntu host",
)


def test_systemd_is_really_pid_one() -> None:
    assert Path("/proc/1/comm").read_text().strip() == "systemd"
    assert subprocess.run(["systemctl", "is-system-running", "--wait"], timeout=20).returncode in {
        0,
        1,
    }


def test_user_transient_unit_survives_launcher(tmp_path: Path) -> None:
    unit = f"localflow-target-{os.getpid()}"
    result = tmp_path / "finished"
    command = [
        "systemd-run",
        "--user",
        "--unit",
        unit,
        "--collect",
        "/bin/sh",
        "-c",
        f"sleep 1; printf done > {result}",
    ]
    launched = subprocess.run(command, capture_output=True, text=True)
    assert launched.returncode == 0, launched.stderr
    for _ in range(50):
        if result.exists():
            break
        time.sleep(0.1)
    assert result.read_text() == "done"
