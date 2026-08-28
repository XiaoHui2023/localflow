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
