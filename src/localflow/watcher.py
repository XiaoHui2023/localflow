from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from watchfiles import awatch

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
        self._config_versions = self._scan_config_versions()
        self._plugin_versions = self._scan_plugin_versions()

    def _scan_config_versions(self) -> dict[str, str]:
        versions: dict[str, str] = {}
        for relative in self.config.list():
            try:
                item = self.config.read(relative)
                versions[relative] = item.version
            except (OSError, ValueError):
                continue
        return versions

    def _scan_plugin_versions(self) -> dict[str, str]:
        versions: dict[str, str] = {}
        directory = self.root / "plugins"

        def visit(path: Path, relative: Path, ancestors: frozenset[tuple[int, int]]) -> None:
            try:
                stat = path.stat()
                identity = (stat.st_dev, stat.st_ino)
                if identity in ancestors:
                    return
                entries = sorted(path.iterdir(), key=lambda item: item.name.casefold())
            except OSError:
                return
            for entry in entries:
                if entry.name == "__pycache__" or entry.name.startswith(".localflow-"):
                    continue
                logical = relative / entry.name
                try:
                    if entry.is_dir():
                        visit(entry, logical, ancestors | {identity})
                    elif entry.is_file() and entry.suffix.lower() in {".py", ".md"}:
                        versions[logical.as_posix()] = hashlib.sha256(
                            entry.read_bytes()
                        ).hexdigest()
                except OSError:
                    continue

        visit(directory, Path(), frozenset())
        return versions

    async def run(self) -> None:
        async for _changes in awatch(
            self.root / "config",
            self.root / "plugins",
            stop_event=self.stop_event,
            debounce=200,
            step=50,
            rust_timeout=1000,
            yield_on_timeout=True,
        ):
            # A bounded reconciliation is intentional: native watchers differ in
            # whether they follow nested symbolic links.  The one-second fallback
            # makes link targets and AI-authored disk edits observable everywhere.
            current = self._scan_config_versions()
            for relative in self._config_versions.keys() - current.keys():
                self.store.append_event(None, "config.deleted", {"path": relative})
            for relative, version in current.items():
                if self._config_versions.get(relative) == version:
                    continue
                try:
                    content = self.config.read(relative).content
                    self.config.validate(relative, content)
                    self.store.append_event(
                        None, "config.changed", {"path": relative, "version": version}
                    )
                except Exception as exc:
                    self.store.append_event(
                        None,
                        "config.invalid",
                        {"path": relative, "error": f"{type(exc).__name__}: {exc}"},
                    )
            self._config_versions = current
            plugin_versions = self._scan_plugin_versions()
            if plugin_versions != self._plugin_versions:
                changed_paths = sorted(
                    path
                    for path in plugin_versions.keys() | self._plugin_versions.keys()
                    if plugin_versions.get(path) != self._plugin_versions.get(path)
                )
                self.plugins.load()
                self._plugin_versions = plugin_versions
                self.store.append_event(
                    None,
                    "plugins.changed",
                    {
                        "generation": self.plugins.generation,
                        "diagnostics": self.plugins.diagnostics,
                        "paths": changed_paths,
                    },
                )

    def stop(self) -> None:
        self.stop_event.set()
