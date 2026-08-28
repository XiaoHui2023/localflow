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
        # Keep the lexical root as well as its target.  A release may deliberately
        # make config/ (or descendants) symbolic links managed elsewhere.
        self.root = root / "config"
        self._diagnose = diagnose

    def _path(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or not relative or any(part in {"", ".", ".."} for part in candidate.parts):
            raise ValueError("config path escapes config directory")
        path = self.root.joinpath(*candidate.parts)
        if path.suffix.lower() not in {".yaml", ".yml", ".toml", ".json"}:
            raise ValueError("unsupported config format")
        return path

    def _resolve(self, relative: str) -> Path:
        """Resolve content access while leaving the directory entry untouched."""
        return self._path(relative).resolve()

    @staticmethod
    def _version(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def list(self) -> list[str]:
        found: list[str] = []

        def visit(directory: Path, relative: Path, ancestors: frozenset[tuple[int, int]]) -> None:
            try:
                stat = directory.stat()
                identity = (stat.st_dev, stat.st_ino)
                if identity in ancestors:
                    return
                next_ancestors = ancestors | {identity}
                entries = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
            except (FileNotFoundError, NotADirectoryError, OSError):
                return
            for entry in entries:
                logical = relative / entry.name
                try:
                    if entry.is_dir():
                        visit(entry, logical, next_ancestors)
                    elif entry.is_file() and entry.suffix.lower() in {".yaml", ".yml", ".toml", ".json"}:
                        found.append(logical.as_posix())
                except OSError:
                    continue

        visit(self.root, Path(), frozenset())
        return sorted(found)

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
        if self._diagnose is not None:
            diagnosis = self._diagnose(parsed)
            if diagnosis.kind != "generic" and not diagnosis.valid:
                raise ValueError("; ".join(diagnosis.errors))
        return parsed

    def write(self, relative: str, content: str, expected: str | None) -> ConfigFile:
        logical_path = self._path(relative)
        path = logical_path.resolve() if logical_path.is_symlink() else logical_path
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
        source_path = self._path(source)
        target_path = self._path(target)
        if source_path == target_path:
            return self.read(source)
        current = self.read(source)
        if current.version != expected:
            raise ConfigConflict(current.version)
        if target_path.exists():
            raise FileExistsError(target)
        if source_path.is_symlink():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.rename(target_path)
            return self.read(target)
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
        path = self._path(relative)
        current = self.read(relative)
        if current.version != expected:
            raise ConfigConflict(current.version)
        path.unlink()
