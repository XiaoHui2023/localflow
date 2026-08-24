from __future__ import annotations

import asyncio
from pathlib import Path

from watchfiles import Change, awatch

from .config_repository import ConfigRepository
from .plugins import PluginRegistry
from .storage import Store


class DirectoryWatcher:
    def __init__(
        self,
        root: Path,
        store: Store,
        config: ConfigRepository,
        plugins: PluginRegistry,
    ) -> None:
        self.root = root
        self.store = store
        self.config = config
        self.plugins = plugins
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        async for changes in awatch(
            self.root / "config",
            self.root / "plugins",
            stop_event=self.stop_event,
            debounce=200,
            step=50,
        ):
            plugin_changed = False
            for change, raw_path in changes:
                path = Path(raw_path).resolve()
                if (self.root / "plugins").resolve() in path.parents:
                    plugin_changed = True
                    continue
                if (self.root / "config").resolve() not in path.parents:
                    continue
                relative = str(path.relative_to(self.root / "config")).replace("\\", "/")
                if change == Change.deleted:
                    self.store.append_event(None, "config.deleted", {"path": relative})
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                    self.config.validate(relative, content)
                    version = self.config._version(content)
                    self.store.append_event(
                        None, "config.changed", {"path": relative, "version": version}
                    )
                except Exception as exc:
                    self.store.append_event(
                        None,
                        "config.invalid",
                        {"path": relative, "error": f"{type(exc).__name__}: {exc}"},
                    )
            if plugin_changed:
                self.plugins.load()
                self.store.append_event(
                    None,
                    "plugins.changed",
                    {
                        "generation": self.plugins.generation,
                        "diagnostics": self.plugins.diagnostics,
                    },
                )

    def stop(self) -> None:
        self.stop_event.set()
