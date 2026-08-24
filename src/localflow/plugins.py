from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import TaskCreate

_loading: list[tuple[str, str, type]] | None = None


def plugin(name: str, *, version: str = "1"):
    def decorate(cls: type) -> type:
        if _loading is None:
            raise RuntimeError("@plugin can only register while LocalFlow loads a plugin file")
        _loading.append((name, version, cls))
        return cls

    return decorate


class TemplatePlugin(Protocol):
    fields: list[dict[str, Any]]

    def discover(self, context: dict[str, Any]) -> list[str]: ...
    def expand(self, values: dict[str, Any], context: dict[str, Any]) -> list[TaskCreate]: ...


@dataclass(frozen=True)
class LoadedPlugin:
    name: str
    version: str
    digest: str
    generation: int
    instance: TemplatePlugin
    path: str


class PluginRegistry:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.generation = 0
        self.plugins: dict[str, LoadedPlugin] = {}
        self.diagnostics: dict[str, str] = {}

    def load(self) -> None:
        global _loading
        candidates: dict[str, LoadedPlugin] = {}
        diagnostics: dict[str, str] = {}
        generation = self.generation + 1
        for path in sorted(self.directory.glob("*.py")):
            registrations: list[tuple[str, str, type]] = []
            _loading = registrations
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                module_name = f"localflow_user_plugin_{generation}_{path.stem}_{digest[:8]}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"cannot load {path}")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                for name, version, cls in registrations:
                    if name in candidates:
                        raise ValueError(f"duplicate plugin name: {name}")
                    instance = cls()
                    if not hasattr(instance, "fields") or not callable(
                        getattr(instance, "expand", None)
                    ):
                        raise TypeError(f"plugin {name} must define fields and expand")
                    candidates[name] = LoadedPlugin(
                        name, version, digest, generation, instance, str(path)
                    )
            except Exception as exc:
                diagnostics[str(path)] = f"{type(exc).__name__}: {exc}"
            finally:
                _loading = None
        if candidates or not self.plugins:
            self.plugins = candidates
            self.generation = generation
        self.diagnostics = diagnostics

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "version": item.version,
                "digest": item.digest,
                "generation": item.generation,
                "fields": item.instance.fields,
            }
            for item in self.plugins.values()
        ]

    def expand(
        self, name: str, values: dict[str, Any], context: dict[str, Any]
    ) -> list[TaskCreate]:
        loaded = self.plugins[name]
        drafts = loaded.instance.expand(values, context)
        snapshot = {
            "name": name,
            "version": loaded.version,
            "digest": loaded.digest,
            "generation": loaded.generation,
            "values": values,
        }
        return [
            draft.model_copy(update={"plugin_snapshot": snapshot, "template": name})
            for draft in drafts
        ]

    async def discover(
        self, name: str, values: dict[str, Any], timeout_seconds: float = 5
    ) -> list[str]:
        loaded = self.plugins[name]
        method = getattr(loaded.instance, "discover", None)
        if not callable(method):
            return []
        result = await asyncio.wait_for(asyncio.to_thread(method, values), timeout=timeout_seconds)
        if not isinstance(result, list) or any(not isinstance(item, str) for item in result):
            raise TypeError("plugin discover must return a list of strings")
        return result
