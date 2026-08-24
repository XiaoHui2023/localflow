from json import JSONDecodeError
from pathlib import Path

import pytest

from localflow.config_repository import ConfigConflict, ConfigRepository
from localflow.settings import initialize_root


def test_config_conditional_atomic_write(root: Path) -> None:
    initialize_root(root)
    repository = ConfigRepository(root)
    before = repository.read("server.yaml")
    saved = repository.write("server.yaml", "server:\n  port: 1234\n", before.version)
    assert saved.version != before.version
    with pytest.raises(ConfigConflict):
        repository.write("server.yaml", "server: {}\n", before.version)
    assert repository.read("server.yaml").content == "server:\n  port: 1234\n"


def test_config_rejects_escape_and_invalid_content(root: Path) -> None:
    initialize_root(root)
    repository = ConfigRepository(root)
    with pytest.raises(ValueError):
        repository.write("../outside.yaml", "x: 1", None)
    with pytest.raises(JSONDecodeError):
        repository.write("broken.json", "{", None)
    assert not (root / "config" / "broken.json").exists()
    server = repository.read("server.yaml")
    with pytest.raises(ValueError):
        repository.write("server.yaml", "server:\n  port: 99999\n", server.version)
    assert repository.read("server.yaml").content == server.content


def test_interrupted_atomic_replace_preserves_original(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_root(root)
    repository = ConfigRepository(root)
    before = repository.read("server.yaml")

    def fail_replace(_source, _target) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr("localflow.config_repository.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        repository.write("server.yaml", "server:\n  port: 1234\n", before.version)
    assert repository.read("server.yaml") == before
    assert not list((root / "config").glob(".server.yaml.*"))
