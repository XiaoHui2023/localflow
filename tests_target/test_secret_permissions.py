from __future__ import annotations

import os
from pathlib import Path
from stat import S_IMODE

import pytest

from localflow.auth import AuthManager
from localflow.settings import initialize_root

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX mode contract")


def _mode(path: Path) -> int:
    return S_IMODE(path.stat().st_mode)


def test_secret_modes_are_set_once_then_left_under_operator_control(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    initialize_root(root)
    AuthManager(root)

    directory = root / "secrets"
    api_key = directory / "api-key"
    admin_key = directory / "web-admin-key"
    assert _mode(directory) == 0o700
    assert _mode(api_key) == 0o600
    assert _mode(admin_key) == 0o600

    original_api_key = api_key.read_bytes()
    original_admin_key = admin_key.read_bytes()
    os.chmod(directory, 0o750)
    os.chmod(api_key, 0o644)
    os.chmod(admin_key, 0o640)

    initialize_root(root)
    restarted = AuthManager(root)

    assert _mode(directory) == 0o750
    assert _mode(api_key) == 0o644
    assert _mode(admin_key) == 0o640
    assert api_key.read_bytes() == original_api_key
    assert admin_key.read_bytes() == original_admin_key

    restarted.rotate_api_key()
    assert _mode(api_key) == 0o644
    assert api_key.read_bytes() != original_api_key


def test_missing_secret_is_created_securely_without_touching_existing_state(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    initialize_root(root)
    AuthManager(root)
    directory = root / "secrets"
    api_key = directory / "api-key"
    admin_key = directory / "web-admin-key"
    original_admin_key = admin_key.read_bytes()
    os.chmod(directory, 0o755)
    os.chmod(admin_key, 0o644)
    api_key.unlink()

    AuthManager(root)

    assert _mode(directory) == 0o755
    assert _mode(admin_key) == 0o644
    assert admin_key.read_bytes() == original_admin_key
    assert _mode(api_key) == 0o600
