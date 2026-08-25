from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from configlib import load_config_raw

from .config_diagnostics import ConfigDiagnosis
from .settings import Settings


@dataclass(frozen=True)
class ConfigFile:
    path: str
    content: str
    version: str


class ConfigConflict(Exception):
    pass


class ConfigRepository:
    _include_pattern = re.compile(r"!include\s+([^#\r\n]+)")

    def __init__(
        self,
        root: Path,
        diagnose: Callable[[Any], ConfigDiagnosis] | None = None,
    ) -> None:
        self.root = (root / "config").resolve()
        self._diagnose = diagnose

    def _resolve(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if path == self.root or self.root not in path.parents:
            raise ValueError("config path escapes config directory")
        if path.suffix.lower() not in {".yaml", ".yml", ".toml", ".json"}:
            raise ValueError("unsupported config format")
        return path

    @staticmethod
    def _version(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def list(self) -> list[str]:
        return sorted(
            str(path.relative_to(self.root)).replace("\\", "/")
            for path in self.root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".yaml", ".yml", ".toml", ".json"}
        )

    def read(self, relative: str) -> ConfigFile:
        path = self._resolve(relative)
        content = path.read_text(encoding="utf-8")
        return ConfigFile(relative, content, self._version(content))

    def _check_includes(self, path: Path, content: str, visited: set[Path]) -> None:
        if path.suffix.lower() not in {".yaml", ".yml"}:
            return
        for match in self._include_pattern.finditer(content):
            for raw in match.group(1).split():
                relative = raw.strip("'\"")
                included = (path.parent / relative).resolve()
                if included == self.root or self.root not in included.parents:
                    raise ValueError("included config escapes config directory")
                if included.suffix.lower() not in {".yaml", ".yml", ".toml", ".json"}:
                    raise ValueError(f"unsupported included config format: {relative}")
                if not included.is_file():
                    raise ValueError(f"included config does not exist: {relative}")
                if included not in visited:
                    visited.add(included)
                    self._check_includes(
                        included, included.read_text(encoding="utf-8"), visited
                    )

    def parse(self, relative: str, content: str | None = None) -> Any:
        path = self._resolve(relative)
        source = path.read_text(encoding="utf-8") if content is None else content
        self._check_includes(path, source, {path})
        if content is None:
            return load_config_raw(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.stem}.validate.", suffix=path.suffix, dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
            return load_config_raw(temporary)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def validate(self, relative: str, content: str) -> object:
        parsed = self.parse(relative, content)
        if relative == "server.yaml":
            Settings.model_validate(parsed or {})
        if self._diagnose is not None:
            diagnosis = self._diagnose(parsed)
            if diagnosis.kind != "generic" and not diagnosis.valid:
                raise ValueError("; ".join(diagnosis.errors))
        return parsed

    def write(self, relative: str, content: str, expected: str | None) -> ConfigFile:
        path = self._resolve(relative)
        if path.exists():
            current = self.read(relative)
            if expected is None or current.version != expected:
                raise ConfigConflict(current.version)
        elif expected not in {None, "*"}:
            raise ConfigConflict("missing")
        self.validate(relative, content)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                os.chmod(temp_name, 0o640)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return self.read(relative)

    def move(self, source: str, target: str, expected: str) -> ConfigFile:
        source_path = self._resolve(source)
        target_path = self._resolve(target)
        if source_path == target_path:
            return self.read(source)
        current = self.read(source)
        if current.version != expected:
            raise ConfigConflict(current.version)
        if target_path.exists():
            raise FileExistsError(target)
        content = current.content
        if source_path.parent != target_path.parent and source_path.suffix.lower() in {".yaml", ".yml"}:
            def relocate(match: re.Match[str]) -> str:
                rewritten = []
                for raw in match.group(1).split():
                    quote = raw[0] if raw[:1] in {"'", '"'} else ""
                    relative = raw.strip("'\"")
                    included = (source_path.parent / relative).resolve()
                    moved_relative = os.path.relpath(included, target_path.parent).replace("\\", "/")
                    rewritten.append(f"{quote}{moved_relative}{quote}")
                return "!include " + " ".join(rewritten)

            content = self._include_pattern.sub(relocate, content)
        self.validate(target, content)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{target_path.name}.", dir=target_path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                os.chmod(temp_name, 0o640)
            os.replace(temp_name, target_path)
            source_path.unlink()
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return self.read(target)

    def delete(self, relative: str, expected: str) -> None:
        path = self._resolve(relative)
        current = self.read(relative)
        if current.version != expected:
            raise ConfigConflict(current.version)
        path.unlink()
