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
    roots = {item["path"] for item in repository.entries() if item.get("readonly")}
    assert roots == {"config", "plugins"}

    repository.create_directory("plugins/helpers")
    (root / "plugins" / "__pycache__").mkdir()
    (root / "plugins" / "__pycache__" / "tool.py").write_text("generated\n", encoding="utf-8")
    assert not any("__pycache__" in str(item["path"]) for item in repository.entries())
    plugin = repository.write("plugins/helpers/tool.py", "VALUE = 1\n", "*")
    with pytest.raises(WorkspaceConflict):
        repository.write(plugin.path, "VALUE = 2\n", "stale")
    with pytest.raises(SyntaxError):
        repository.write(plugin.path, "if:\n", plugin.version)
    assert repository.read(plugin.path).content == "VALUE = 1\n"

    repository.copy("plugins/helpers/tool.py", "plugins/helpers/copy.py")
    repository.move("plugins/helpers/copy.py", "plugins/moved.py")
    repository.delete("plugins/moved.py")
    assert not (root / "plugins" / "moved.py").exists()
    with pytest.raises(ValueError, match="unsupported"):
        repository.copy("plugins/helpers/tool.py", "plugins/helpers/tool.txt")
    with pytest.raises(ValueError, match="inside itself"):
        repository.copy("plugins/helpers", "plugins/helpers/nested")


def test_workspace_rolls_back_move_that_breaks_config_import(root: Path) -> None:
    initialize_root(root)
    config = ConfigRepository(root)
    config.write("shared/value.yaml", "labels: [shared]\n", None)
    config.write(
        "command/imported.yaml",
        "!include ../shared/value.yaml\nplugin: command\nname: imported\nworking_directory: .\ncommand: true\n",
        None,
    )
    repository = WorkspaceRepository(root, config)
    with pytest.raises(ValueError, match="breaks configuration imports"):
        repository.move("config/shared/value.yaml", "config/shared/renamed.yaml")
    assert (root / "config" / "shared" / "value.yaml").is_file()
    assert config.parse("command/imported.yaml")["labels"] == ["shared"]


@pytest.mark.skipif(os.name == "nt", reason="Linux release symlink semantics")
def test_workspace_preserves_symlink_copy_edit_move_and_delete(root: Path, tmp_path: Path) -> None:
    initialize_root(root)
    target = tmp_path / "external.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    link = root / "plugins" / "external.py"
    link.symlink_to(target)
    repository = WorkspaceRepository(root, ConfigRepository(root))

    item = repository.read("plugins/external.py")
    repository.write(item.path, "VALUE = 2\n", item.version)
    repository.copy(item.path, "plugins/copy.py")
    assert link.is_symlink() and (root / "plugins" / "copy.py").is_symlink()
    repository.move(item.path, "plugins/moved.py")
    repository.delete("plugins/moved.py")
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"


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
    repository.write("plugins/demo.py", "VALUE = 1\n", "*")

    roots = {item["path"]: item for item in repository.entries() if item.get("readonly")}
    assert roots["config"]["symlink"] is True
    assert roots["plugins"]["symlink"] is True
    assert (root / "config").is_symlink() and (root / "plugins").is_symlink()
    assert (external_config / "command" / "demo.yaml").is_file()
    assert (external_plugins / "demo.py").is_file()


def test_workspace_api_round_trip(admin: TestClient) -> None:
    listing = admin.get("/api/v1/workspace")
    assert listing.status_code == 200
    assert {item["path"] for item in listing.json()["items"]}.issuperset({"config", "plugins"})
    assert admin.post("/api/v1/workspace/directories", json={"path": "plugins/helpers"}).status_code == 201
    created = admin.put(
        "/api/v1/workspace/files/plugins/helpers/tool.py",
        headers={"If-Match": "*"},
        json={"content": "VALUE = 1\n"},
    )
    assert created.status_code == 200
    copied = admin.post(
        "/api/v1/workspace/copies",
        json={"source": "plugins/helpers/tool.py", "target": "plugins/helpers/copy.py"},
    )
    assert copied.status_code == 201
    assert admin.delete("/api/v1/workspace/entries/plugins/helpers/copy.py").status_code == 204
