import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from localflow.config_diagnostics import diagnose_config
from localflow.config_repository import ConfigConflict, ConfigRepository
from localflow.plugins import PluginRegistry
from localflow.settings import initialize_root


def test_config_conditional_atomic_write(root: Path) -> None:
    initialize_root(root)
    repository = ConfigRepository(root)
    before = repository.read("command/hello-world.yaml")
    saved = repository.write(
        before.path, before.content.replace("hello-world.txt", "hello.txt"), before.version
    )
    assert saved.version != before.version
    with pytest.raises(ConfigConflict):
        repository.write(before.path, before.content, before.version)


@pytest.mark.skipif(os.name == "nt", reason="Linux release symlink semantics")
def test_config_preserves_file_and_directory_symlinks(root: Path, tmp_path: Path) -> None:
    initialize_root(root)
    external = tmp_path / "managed-elsewhere"
    external.mkdir()
    target = external / "linked.yaml"
    target.write_text("name: before\n", encoding="utf-8")
    link = root / "config" / "linked.yaml"
    link.symlink_to(target)
    linked_directory = root / "config" / "linked-directory"
    linked_directory.symlink_to(external, target_is_directory=True)

    repository = ConfigRepository(root)
    assert {"linked.yaml", "linked-directory/linked.yaml"}.issubset(repository.list())
    before = repository.read("linked.yaml")
    repository.write("linked.yaml", "name: after\n", before.version)
    assert link.is_symlink() and target.read_text(encoding="utf-8") == "name: after\n"

    moved = repository.move("linked.yaml", "renamed-link.yaml", repository.read("linked.yaml").version)
    assert not link.exists() and (root / "config" / "renamed-link.yaml").is_symlink()
    repository.delete(moved.path, moved.version)
    assert target.is_file() and not (root / "config" / "renamed-link.yaml").exists()


def test_config_rejects_escape_invalid_content_and_preserves_atomic_write(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_root(root)
    repository = ConfigRepository(root)
    with pytest.raises(ValueError):
        repository.write("../outside.yaml", "x: 1", None)
    with pytest.raises(ValueError):
        repository.write("broken.json", "{", None)
    before = repository.read("command/hello-world.yaml")

    def fail_replace(_source, _target) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr("localflow.config_repository.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        repository.write(before.path, before.content + "\n", before.version)
    assert repository.read(before.path) == before


def test_task_config_move_rename_delete_and_import(root: Path) -> None:
    initialize_root(root)
    repository = ConfigRepository(root)
    original = repository.read("command/hello-world.yaml")
    moved = repository.move(original.path, "command/renamed.yaml", original.version)
    with pytest.raises(ConfigConflict):
        repository.delete(moved.path, "stale-version")
    repository.delete(moved.path, moved.version)

    repository.write("shared/names.yaml", "labels: [shared]\n", None)
    task = repository.write(
        "command/imported.yaml",
        "!include ../shared/names.yaml\nplugin: command\nname: imported\nworking_directory: .\ncommand: [true]\n",
        None,
    )
    assert repository.parse(task.path)["labels"] == ["shared"]


def test_config_imports_and_layered_diagnosis(root: Path) -> None:
    initialize_root(root)
    plugins = PluginRegistry(root / "plugins")
    plugins.load()
    repository = ConfigRepository(root, lambda value: diagnose_config(value, plugins))
    assert diagnose_config({"database": {"pool": 2}}, plugins).kind == "generic"
    assert diagnose_config({"labels": ["shared"]}, plugins).kind == "fragment"
    task = diagnose_config(repository.parse("command/hello-world.yaml"), plugins)
    assert (task.valid, task.runnable, task.plugin) == (True, True, "command")
    invalid = diagnose_config({"plugin": "verification", "command": ["python3"]}, plugins)
    assert not invalid.valid and any("case_directory" in item for item in invalid.errors)


def test_config_api_exposes_only_runnable_configuration_tree(admin: TestClient, root: Path) -> None:
    valid = admin.get("/api/v1/config/files/command/hello-world.yaml")
    assert valid.status_code == 200 and valid.json()["diagnosis"]["runnable"]
    invalid_path = root / "config" / "command" / "invalid.yaml"
    invalid_path.write_text("plugin: command\nlabels: wrong\n", encoding="utf-8")
    invalid = admin.get("/api/v1/config/files/command/invalid.yaml")
    assert invalid.status_code == 200 and not invalid.json()["diagnosis"]["valid"]
    listing = admin.get("/api/v1/config/files").json()
    assert "server.yaml" not in listing["items"]
    assert set(listing["items"]) == {
        "command/hello-world.yaml",
        "command/invalid.yaml",
        "verification/demo.yaml",
    }

    inspection = admin.post(
        "/api/v1/config/files/verification/demo.yaml/inspection", json={"inputs": {}}
    )
    assert inspection.status_code == 200
    items = {item["name"]: item for item in inspection.json()["items"]}
    assert items["working_directory"]["severity"] == "ok"
    assert items["case_directory"]["severity"] == "ok"
    assert items["command_file"]["severity"] == "ok"

    broken = root / "config" / "verification" / "broken-path.yaml"
    broken.write_text(
        "plugin: verification\ncase_directory: missing\nworking_directory: nowhere\ncommand: [missing-command]\n",
        encoding="utf-8",
    )
    failed = admin.post(
        "/api/v1/config/files/verification/broken-path.yaml/inspection",
        json={"inputs": {}},
    )
    assert failed.status_code == 200
    assert {item["name"] for item in failed.json()["items"] if item["severity"] == "error"} == {
        "working_directory",
        "command",
        "case_directory",
    }


def test_config_api_covers_create_read_write_move_and_delete(admin: TestClient) -> None:
    created = admin.post(
        "/api/v1/config/files", json={"path": "command/api-created.yaml", "plugin": "command"}
    )
    assert created.status_code == 201
    read = admin.get("/api/v1/config/files/command/api-created.yaml")
    updated = admin.put(
        "/api/v1/config/files/command/api-created.yaml",
        headers={"If-Match": read.json()["version"]},
        json={"content": read.json()["content"].replace("hello-world", "api-command")},
    )
    assert updated.status_code == 200
    moved = admin.post(
        "/api/v1/config/files/command/api-created.yaml/move",
        json={"target": "command/api-renamed.yaml", "version": updated.json()["version"]},
    )
    deleted = admin.delete(
        "/api/v1/config/files/command/api-renamed.yaml",
        headers={"If-Match": moved.json()["version"]},
    )
    assert deleted.status_code == 204
