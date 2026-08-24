from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .settings import Settings, parse_config


@dataclass(frozen=True)
class ConfigFile:
    path: str
    content: str
    version: str


class ConfigConflict(Exception):
    pass


class ConfigRepository:
    def __init__(self, root: Path) -> None:
        self.root = (root / "config").resolve()

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

    def validate(self, relative: str, content: str) -> object:
        path = self._resolve(relative)
        parsed = parse_config(path, content)
        if relative == "server.yaml":
            Settings.model_validate(parsed or {})
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
