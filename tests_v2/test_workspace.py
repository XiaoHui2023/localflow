import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from localflow.config_repository import ConfigRepository
from localflow.settings import initialize_root
from localflow.workspace_repository import WorkspaceConflict, WorkspaceRepository


def test_workspace_directory_file_copy_move_delete_and_validation(root: Path) -> None:
    initialize_root(root)
    repository = WorkspaceRepository(root, ConfigRepository(root))
    assert not any(item.get("readonly") for item in repository.entries())

    repository.create_directory("config/helpers")
    (root / "config" / "__pycache__").mkdir()
    (root / "config" / "__pycache__" / "tool.yaml").write_text("generated\n", encoding="utf-8")
    assert not any("__pycache__" in str(item["path"]) for item in repository.entries())
    plugin = repository.write("config/helpers/tool.yaml", "free: edit\n", "*")
    with pytest.raises(WorkspaceConflict):
        repository.write(plugin.path, "free: change\n", "stale")
    repository.write(plugin.path, "if:\n", plugin.version)
    assert repository.read(plugin.path).content == "if:\n"

    repository.copy("config/helpers/tool.yaml", "config/helpers/copy.yaml")
    repository.move("config/helpers/copy.yaml", "config/moved.yaml")
    repository.delete("config/moved.yaml")
    assert not (root / "config" / "moved.yaml").exists()
    with pytest.raises(ValueError, match="unsupported"):
        repository.copy("config/helpers/tool.yaml", "config/helpers/tool.txt")
    with pytest.raises(ValueError, match="inside itself"):
        repository.copy("config/helpers", "config/helpers/nested")


def test_workspace_move_is_independent_from_config_diagnosis(root: Path) -> None:
    initialize_root(root)
    config = ConfigRepository(root)
    config.write("shared/value.yaml", "labels: [shared]\n", None)
    config.write(
        "command/imported.yaml",
        "!include ../shared/value.yaml\nplugin: command\nname: imported\nworking_directory: .\ncommand: true\n",
        None,
    )
    repository = WorkspaceRepository(root, config)
    repository.move("config/shared/value.yaml", "config/shared/renamed.yaml")
    assert (root / "config" / "shared" / "renamed.yaml").is_file()
    with pytest.raises(ValueError, match="does not exist"):
        config.parse("command/imported.yaml")


@pytest.mark.skipif(os.name == "nt", reason="Linux release symlink semantics")
def test_workspace_preserves_symlink_copy_edit_move_and_delete(root: Path, tmp_path: Path) -> None:
    initialize_root(root)
    target = tmp_path / "external.yaml"
    target.write_text("value: 1\n", encoding="utf-8")
    link = root / "config" / "external.yaml"
    link.symlink_to(target)
    repository = WorkspaceRepository(root, ConfigRepository(root))

    item = repository.read("config/external.yaml")
    repository.write(item.path, "value: 2\n", item.version)
    repository.copy(item.path, "config/copy.yaml")
    assert link.is_symlink() and (root / "config" / "copy.yaml").is_symlink()
    repository.move(item.path, "config/moved.yaml")
    repository.delete("config/moved.yaml")
    assert target.read_text(encoding="utf-8") == "value: 2\n"


@pytest.mark.skipif(os.name == "nt", reason="Linux release symlink semantics")
def test_workspace_supports_entire_linked_roots_without_flattening(
    root: Path, tmp_path: Path
) -> None:
    initialize_root(root)
    external_config = tmp_path / "configuration"
    external_plugins = tmp_path / "plugin-source"
    external_config.mkdir()
    external_plugins.mkdir()
    shutil.rmtree(root / "config")
    shutil.rmtree(root / "plugins")
    (root / "config").symlink_to(external_config, target_is_directory=True)
    (root / "plugins").symlink_to(external_plugins, target_is_directory=True)
    repository = WorkspaceRepository(root, ConfigRepository(root))

    repository.create_directory("config/command")
    repository.write("config/command/demo.yaml", "value: 1\n", "*")
    assert all(str(item["path"]).startswith("config/") for item in repository.entries())
    assert (root / "config").is_symlink() and (root / "plugins").is_symlink()
    assert (external_config / "command" / "demo.yaml").is_file()


def test_workspace_api_round_trip(admin: TestClient) -> None:
    listing = admin.get("/api/v1/workspace")
    assert listing.status_code == 200
    assert all(item["path"].startswith("config/") for item in listing.json()["items"])
    assert admin.post("/api/v1/workspace/directories", json={"path": "config/helpers"}).status_code == 201
    created = admin.put(
        "/api/v1/workspace/files/config/helpers/tool.yaml",
        headers={"If-Match": "*"},
        json={"content": "value: 1\n"},
    )
    assert created.status_code == 200
    copied = admin.post(
        "/api/v1/workspace/copies",
        json={"source": "config/helpers/tool.yaml", "target": "config/helpers/copy.yaml"},
    )
    assert copied.status_code == 201
    assert admin.delete("/api/v1/workspace/entries/config/helpers/copy.yaml").status_code == 204
