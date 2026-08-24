from __future__ import annotations

import asyncio
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
