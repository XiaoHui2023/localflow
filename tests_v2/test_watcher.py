from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from localflow.config_repository import ConfigRepository
from localflow.plugins import PluginRegistry
from localflow.settings import initialize_root
from localflow.storage import Store
from localflow.watcher import DirectoryWatcher


@pytest.mark.asyncio
async def test_external_config_change_and_invalid_file_emit_events(root: Path) -> None:
    initialize_root(root)
    store = Store(root / "runtime" / "localflow.db")
    watcher = DirectoryWatcher(
        root, store, ConfigRepository(root), PluginRegistry(root / "plugins")
    )
    running = asyncio.create_task(watcher.run())
    await asyncio.sleep(0.15)
    path = root / "config" / "external.yaml"
    path.write_text("value: 1\n", encoding="utf-8")
    for _ in range(50):
        await asyncio.sleep(0.05)
        if any(item.kind == "config.changed" for item in store.events_after(0)):
            break
    broken = root / "config" / "broken.yaml"
    broken.write_text("value: [\n", encoding="utf-8")
    for _ in range(50):
        await asyncio.sleep(0.05)
        if any(item.kind == "config.invalid" for item in store.events_after(0)):
            break
    watcher.stop()
    await running
    kinds = [item.kind for item in store.events_after(0)]
    assert "config.changed" in kinds
    assert "config.invalid" in kinds
    invalid = next(item for item in store.events_after(0) if item.kind == "config.invalid")
    assert invalid.data["path"] == "broken.yaml"
    assert invalid.data["version"] == ConfigRepository(root).read("broken.yaml").version
    store.close()


@pytest.mark.asyncio
async def test_external_nested_include_change_invalidates_every_upstream_config(
    root: Path,
) -> None:
    initialize_root(root)
    shared = root / "config" / "shared"
    shared.mkdir()
    leaf = shared / "leaf.yaml"
    middle = shared / "middle.yaml"
    consumer = root / "config" / "consumer.yaml"
    leaf.write_text("command: echo before\n", encoding="utf-8")
    middle.write_text("!include leaf.yaml\n", encoding="utf-8")
    consumer.write_text(
        "!include shared/middle.yaml\nplugin: command\nworking_directory: .\n",
        encoding="utf-8",
    )
    repository = ConfigRepository(root)
    assert repository.affected_by("shared/leaf.yaml") == [
        "consumer.yaml",
        "shared/leaf.yaml",
        "shared/middle.yaml",
    ]

    store = Store(root / "runtime" / "localflow.db")
    watcher = DirectoryWatcher(root, store, repository, PluginRegistry(root / "plugins"))
    running = asyncio.create_task(watcher.run())
    await asyncio.sleep(0.15)
    leaf.write_text("command: echo after\n", encoding="utf-8")
    for _ in range(50):
        await asyncio.sleep(0.05)
        events = [item for item in store.events_after(0) if item.kind == "config.changed"]
        if events:
            break
    watcher.stop()
    await running
    event = next(item for item in store.events_after(0) if item.kind == "config.changed")
    assert event.data["path"] == "shared/leaf.yaml"
    assert event.data["affected_paths"] == [
        "consumer.yaml",
        "shared/leaf.yaml",
        "shared/middle.yaml",
    ]
    store.close()


@pytest.mark.skipif(os.name == "nt", reason="Linux release symlink semantics")
@pytest.mark.asyncio
async def test_reconciliation_detects_external_symlink_target_edits(
    root: Path, tmp_path: Path
) -> None:
    initialize_root(root)
    external_config = tmp_path / "external.yaml"
    external_config.write_text("value: 1\n", encoding="utf-8")
    (root / "config" / "external.yaml").symlink_to(external_config)
    external_plugins = tmp_path / "plugin-source"
    external_plugins.mkdir()
    plugin_file = external_plugins / "external.py"
    plugin_file.write_text("VALUE = 1\n", encoding="utf-8")
    (root / "plugins" / "linked").symlink_to(external_plugins, target_is_directory=True)

    store = Store(root / "runtime" / "localflow.db")
    registry = PluginRegistry(root / "plugins")
    watcher = DirectoryWatcher(root, store, ConfigRepository(root), registry)
    running = asyncio.create_task(watcher.run())
    await asyncio.sleep(0.15)
    external_config.write_text("value: 2\n", encoding="utf-8")
    plugin_file.write_text("VALUE = 2\n", encoding="utf-8")
    for _ in range(40):
        await asyncio.sleep(0.1)
        kinds = {item.kind for item in store.events_after(0)}
        if {"config.changed", "plugins.changed"}.issubset(kinds):
            break
    watcher.stop()
    await running
    events = store.events_after(0)
    kinds = {item.kind for item in events}
    assert {"config.changed", "plugins.changed"}.issubset(kinds)
    plugin_event = next(item for item in events if item.kind == "plugins.changed")
    assert plugin_event.data["paths"] == ["linked/external.py"]
    store.close()
