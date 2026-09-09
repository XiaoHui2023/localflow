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
    broken = repository.write("broken.json", "{", None)
    assert broken.content == "{"
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
    assert not any("${case}" in item or "${seed}" in item for item in invalid.errors)
    assert not invalid.valid and any("case_directory" in item for item in invalid.errors)
    assert any("working_directory" in item for item in invalid.errors)
    extensible = diagnose_config(
        {
            "plugin": "verification",
            "case_directory": "cases",
            "working_directory": ".",
            "command": "true",
            "root": "site-owned-simulation-root",
            "extra_inputs": {"wave": "dump.fsdb"},
        },
        plugins,
    )
    assert extensible.runnable, extensible.errors
    command_extensible = diagnose_config(
        {
            "plugin": "command",
            "name": "site command",
            "working_directory": ".",
            "command": "echo ${site_message}",
            "site_message": "hello from a site-owned variable",
            "extra_inputs": {"toolchain": "custom"},
        },
        plugins,
    )
    assert command_extensible.runnable, command_extensible.errors

    for implicit_name in ("root", "scripts_dir", "cases_dir"):
        implicit = diagnose_config(
            {
                "plugin": "command",
                "name": "portable command",
                "working_directory": ".",
                "command": f"echo ${{{implicit_name}}}",
            },
            plugins,
        )
        assert not implicit.runnable
        assert any(
            f"unknown variable: {implicit_name}" in item for item in implicit.errors
        )
    explicit_root = diagnose_config(
        {
            "plugin": "command",
            "name": "explicit site root",
            "working_directory": ".",
            "command": "echo ${root}",
            "root": "/srv/site-owned",
        },
        plugins,
    )
    assert explicit_root.runnable, explicit_root.errors

    unknown_variable = diagnose_config(
        {
            "plugin": "verification",
            "case_directory": "cases",
            "working_directory": ".",
            "command": "echo ${missing}",
        },
        plugins,
    )
    assert not unknown_variable.runnable
    assert any("unknown variable: missing" in item for item in unknown_variable.errors)
    deferred_variables = diagnose_config(
        {
            "plugin": "verification",
            "case_directory": "cases",
            "working_directory": ".",
            "command": "echo ${case} ${seed}",
        },
        plugins,
    )
    assert deferred_variables.runnable, deferred_variables.errors


def test_third_party_forbid_model_validates_only_its_declared_fields(root: Path) -> None:
    initialize_root(root)
    (root / "plugins" / "site.py").write_text(
        "from pydantic import BaseModel, ConfigDict\n"
        "from localflow.plugins import plugin\n"
        "class Config(BaseModel):\n"
        " model_config=ConfigDict(extra='forbid')\n"
        " tool: str\n"
        "@plugin('site')\n"
        "class Site:\n"
        " config_model=Config\n"
        " required_common_fields={'working_directory','command'}\n"
        " run_fields=[]\n"
        " def expand(self, values, context): return []\n",
        encoding="utf-8",
    )
    plugins = PluginRegistry(root / "plugins")
    plugins.load()
    diagnosis = diagnose_config(
        {
            "plugin": "site",
            "working_directory": ".",
            "command": "echo ${site_value}",
            "tool": "simulator",
            "site_value": "custom",
            "extra_inputs": {"wave": True},
        },
        plugins,
    )
    assert diagnosis.runnable, diagnosis.errors
    site = next(item for item in plugins.describe() if item["name"] == "site")
    assert site["api"]["configuration_schema"]["additionalProperties"] is True
    assert site["api"]["plugin_fields_schema"]["additionalProperties"] is True


def test_folded_shell_command_never_leaks_configlib_composition_sentinels(
    root: Path,
) -> None:
    initialize_root(root)
    source = root / "config" / "verification" / "folded-command.yaml"
    source.write_text(
        "plugin: verification\n"
        "case_directory: cases\n"
        "working_directory: .\n"
        "command: >-\n"
        "  make all\n"
        "  CASE=${case}\n"
        "  ${seed}\n",
        encoding="utf-8",
    )
    document = ConfigRepository(root).parse("verification/folded-command.yaml")
    assert document["command"] == "make all CASE=${case} ${seed}"
    assert "__configlib_" not in document["command"]


def test_config_api_exposes_only_runnable_configuration_tree(admin: TestClient, root: Path) -> None:
    valid = admin.get("/api/v1/config/files/command/hello-world.yaml")
    assert valid.status_code == 200 and valid.json()["diagnosis"]["valid"]
    assert valid.json()["run_diagnosis"]["runnable"]
    invalid_path = root / "config" / "command" / "invalid.yaml"
    invalid_path.write_text("plugin: command\nlabels: wrong\n", encoding="utf-8")
    invalid = admin.get("/api/v1/config/files/command/invalid.yaml")
    assert invalid.status_code == 200 and invalid.json()["diagnosis"]["valid"]
    assert not invalid.json()["run_diagnosis"]["valid"]
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
    assert items["working_directory"]["check"] == "availability"
    assert items["case_directory"]["severity"] == "ok"
    assert items["case_directory"]["check"] == "availability"
    assert "shell" not in items
    assert "command_entry" not in items
    assert items["labels"]["kind"] == "tokens"
    assert items["labels"]["value"] == ["verification"]
    assert items["custom_text_0"]["value"] == "Case: ${case}"
    assert items["custom_text_1"]["value"] == "Seed: ${seed}"

    selected = admin.post(
        "/api/v1/config/files/verification/demo.yaml/inspection",
        json={
            "inputs": {
                "cases": ["case-a"],
                "case_runs": {"case-a": 1},
                "seed": 73,
            }
        },
    )
    assert selected.status_code == 200
    selected_items = {item["name"]: item for item in selected.json()["items"]}
    assert selected_items["custom_text_0"]["value"] == "Case: ${case}"
    assert selected_items["custom_text_1"]["value"] == "Seed: ${seed}"

    broken = root / "config" / "verification" / "broken-path.yaml"
    broken.write_text(
        "plugin: verification\ncase_directory: missing\nworking_directory: nowhere\ncommand: [missing-command, '${case}', '${seed}']\n",
        encoding="utf-8",
    )
    failed = admin.post(
        "/api/v1/config/files/verification/broken-path.yaml/inspection",
        json={"inputs": {}},
    )
    assert failed.status_code == 200
    expected_errors = {
        "working_directory",
        "command",
        "case_directory",
    }
    assert {
        item["name"] for item in failed.json()["items"] if item["severity"] == "error"
    } == expected_errors


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
