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
    with pytest.raises(ValueError):
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


def test_task_config_move_rename_and_delete(root: Path) -> None:
    initialize_root(root)
    repository = ConfigRepository(root)
    original = repository.read("tasks/marker-warning.yaml")
    moved = repository.move(
        "tasks/marker-warning.yaml", "tasks/checks/warning.yaml", original.version
    )
    assert moved.path == "tasks/checks/warning.yaml"
    assert not (root / "config" / "tasks" / "marker-warning.yaml").exists()
    with pytest.raises(ConfigConflict):
        repository.delete(moved.path, "stale-version")
    repository.delete(moved.path, moved.version)
    assert not (root / "config" / moved.path).exists()


def test_common_fragment_is_allowed_and_move_does_not_overwrite(root: Path) -> None:
    initialize_root(root)
    repository = ConfigRepository(root)
    fragment = repository.write("shared/names.yaml", "name: shared\n", None)
    assert repository.parse(fragment.path) == {"name": "shared"}
    source = repository.read("tasks/interactive-shutdown.yaml")
    with pytest.raises(FileExistsError):
        repository.move("tasks/interactive-shutdown.yaml", "tasks/random-number.yaml", source.version)


def test_config_imports_and_layered_diagnosis(root: Path) -> None:
    initialize_root(root)
    plugins = PluginRegistry(root / "plugins")
    plugins.load()
    repository = ConfigRepository(root, lambda value: diagnose_config(value, plugins))

    generic = diagnose_config({"database": {"pool": 2}}, plugins)
    assert (generic.kind, generic.valid, generic.runnable) == ("generic", True, False)
    fragment = diagnose_config({"labels": ["shared"]}, plugins)
    assert (fragment.kind, fragment.valid, fragment.runnable) == ("fragment", True, False)
    invalid_fragment = diagnose_config({"labels": "shared"}, plugins)
    assert invalid_fragment.kind == "fragment" and not invalid_fragment.valid

    expanded = repository.parse("tasks/random-number.yaml")
    task = diagnose_config(expanded, plugins)
    assert (task.kind, task.valid, task.runnable, task.plugin) == (
        "task",
        True,
        True,
        "command",
    )
    assert expanded["custom"]["source"] == "starter"

    invalid_task = diagnose_config(
        {"plugin": "verification", "command": ["python3"]}, plugins
    )
    assert not invalid_task.valid
    assert any("case_directory" in item for item in invalid_task.errors)


def test_config_import_cannot_escape_config_root(root: Path) -> None:
    initialize_root(root)
    outside = root / "outside.yaml"
    outside.write_text("labels: [secret]\n", encoding="utf-8")
    repository = ConfigRepository(root)
    with pytest.raises(ValueError, match="escapes config directory"):
        repository.write("tasks/escape.yaml", "!include ../../outside.yaml\n", None)


def test_config_api_exposes_diagnosis_and_keeps_invalid_files_editable(
    admin: TestClient, root: Path
) -> None:
    valid = admin.get("/api/v1/config/files/tasks/random-number.yaml")
    assert valid.status_code == 200
    diagnosis = valid.json()["diagnosis"]
    assert (diagnosis["kind"], diagnosis["valid"], diagnosis["runnable"]) == (
        "task",
        True,
        True,
    )

    invalid_path = root / "config" / "tasks" / "invalid.yaml"
    invalid_path.write_text("plugin: command\nlabels: wrong\n", encoding="utf-8")
    invalid = admin.get("/api/v1/config/files/tasks/invalid.yaml")
    assert invalid.status_code == 200
    assert invalid.json()["document"] == {"plugin": "command", "labels": "wrong"}
    assert invalid.json()["diagnosis"]["valid"] is False
    assert invalid.json()["diagnosis"]["errors"]

    listing = admin.get("/api/v1/config/files")
    assert listing.status_code == 200
    diagnostics = listing.json()["diagnostics"]
    assert diagnostics["server.yaml"]["kind"] == "generic"
    assert diagnostics["shared/task-defaults.yaml"]["kind"] == "fragment"
    assert diagnostics["tasks/random-number.yaml"]["runnable"] is True
    assert diagnostics["tasks/invalid.yaml"]["valid"] is False

    broken_path = root / "config" / "tasks" / "broken.yaml"
    broken_path.write_text("plugin: [\n", encoding="utf-8")
    broken_listing = admin.get("/api/v1/config/files")
    assert broken_listing.status_code == 200
    broken = broken_listing.json()["diagnostics"]["tasks/broken.yaml"]
    assert broken["valid"] is False
    assert "syntax or import error" in broken["errors"][0]


def test_config_api_covers_create_read_write_move_and_delete(admin: TestClient) -> None:
    created = admin.post(
        "/api/v1/config/files",
        json={"path": "tasks/api-created.yaml", "plugin": "marker"},
    )
    assert created.status_code == 201
    version = created.json()["version"]

    read = admin.get("/api/v1/config/files/tasks/api-created.yaml")
    assert read.status_code == 200
    assert read.json()["plugin"] == "marker"
    assert read.json()["diagnosis"]["runnable"] is True

    updated = admin.put(
        "/api/v1/config/files/tasks/api-created.yaml",
        headers={"If-Match": version},
        json={"content": read.json()["content"].replace("结果检查", "API 检查")},
    )
    assert updated.status_code == 200

    moved = admin.post(
        "/api/v1/config/files/tasks/api-created.yaml/move",
        json={"target": "tasks/api-renamed.yaml", "version": updated.json()["version"]},
    )
    assert moved.status_code == 200
    assert moved.json()["path"] == "tasks/api-renamed.yaml"

    deleted = admin.delete(
        "/api/v1/config/files/tasks/api-renamed.yaml",
        headers={"If-Match": moved.json()["version"]},
    )
    assert deleted.status_code == 204
    assert admin.get("/api/v1/config/files/tasks/api-renamed.yaml").status_code == 404


def test_documented_invalid_config_examples_are_diagnosed_and_cannot_run(
    admin: TestClient, root: Path
) -> None:
    examples = Path(__file__).parents[1] / "examples" / "config-errors"
    for source in examples.glob("*.yaml"):
        (root / "config" / "tasks" / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )

    diagnostics = admin.get("/api/v1/config/files").json()["diagnostics"]
    missing = diagnostics["tasks/missing-field.yaml"]
    wrong = diagnostics["tasks/wrong-type.yaml"]
    syntax = diagnostics["tasks/syntax-error.yaml"]
    assert not missing["valid"] and "case_directory" in " ".join(missing["errors"])
    assert not wrong["valid"] and {"command", "labels"}.issubset(
        {message.split(":", 1)[0] for message in wrong["errors"]}
    )
    assert not syntax["valid"] and "syntax or import error" in syntax["errors"][0]
    for name in ("missing-field", "wrong-type", "syntax-error"):
        response = admin.post(
            f"/api/v1/config/files/tasks/{name}.yaml/runs", json={"inputs": {}}
        )
        assert response.status_code == 422
