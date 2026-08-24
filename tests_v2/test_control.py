import os
from pathlib import Path

from localflow.control import control_socket_path


def test_control_socket_path_stays_below_unix_limit(tmp_path: Path) -> None:
    root = tmp_path / ("very-long-root-" * 12)
    path = control_socket_path(root, "task-" + "x" * 80)
    assert len(str(path).encode()) < 108
    if os.name != "nt":
        assert path.parent.stat().st_mode & 0o077 == 0
