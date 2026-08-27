from __future__ import annotations

import os
from pathlib import Path

import pytest

from localflow.auth import AuthManager
from localflow.settings import initialize_root


def test_secret_files_are_owner_only_and_broad_mode_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    initialize_root(root)
    manager = AuthManager(root)
    assert (root / "secrets").stat().st_mode & 0o077 == 0
    for name in ("api-key", "web-admin-key"):
        assert (root / "secrets" / name).stat().st_mode & 0o077 == 0
    key = root / "secrets" / "api-key"
    os.chmod(key, 0o644)
    with pytest.raises(PermissionError):
        manager.check_permissions()
    os.chmod(key, 0o600)
    os.chmod(root / "secrets", 0o750)
    initialize_root(root)
    assert (root / "secrets").stat().st_mode & 0o077 != 0
    with pytest.raises(PermissionError):
        manager.check_permissions()
