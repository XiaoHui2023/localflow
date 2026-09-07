from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config_repository import ConfigRepository


@dataclass(frozen=True)
class WorkspaceFile:
    path: str
    content: str
    version: str
    symlink: bool


class WorkspaceConflict(Exception):
    pass


class WorkspaceRepository:
    """Configuration workspace limited lexically to ``config/``.

    Resolved symlink targets may live elsewhere because the link itself is the
    user's explicit capability.  User-supplied ``..`` and absolute paths remain
    forbidden, so HTTP paths cannot manufacture access outside those roots.
    """

    _CONFIG_SUFFIXES = {".yaml", ".yml", ".toml", ".json"}

    def __init__(self, root: Path, config: ConfigRepository) -> None:
        self.root = root
        self.config = config

    def _path(self, relative: str, *, allow_root: bool = False) -> Path:
        candidate = Path(relative.replace("\\", "/"))
        parts = candidate.parts
        if candidate.is_absolute() or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("workspace path escapes managed roots")
        if not parts or parts[0] != "config":
            raise ValueError("workspace path must start with config")
        if len(parts) == 1 and not allow_root:
            raise ValueError("workspace root cannot be modified")
        return self.root.joinpath(*parts)

    def _supported(self, path: Path) -> bool:
        return path.suffix.lower() in self._CONFIG_SUFFIXES

    def entries(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []

        def visit(path: Path, logical: Path, ancestors: frozenset[tuple[int, int]]) -> None:
            try:
                stat = path.stat()
                identity = (stat.st_dev, stat.st_ino)
                if identity in ancestors:
                    return
                entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
            except (OSError, NotADirectoryError):
                return
            for item in entries:
                if item.name == "__pycache__" or item.name.startswith(".localflow-"):
                    continue
                child = logical / item.name
                try:
                    is_directory = item.is_dir()
                    if is_directory:
                        result.append({"path": child.as_posix(), "kind": "directory", "symlink": item.is_symlink()})
                        visit(item, child, ancestors | {identity})
                    elif item.is_file() and self._supported(item):
                        result.append({"path": child.as_posix(), "kind": "file", "symlink": item.is_symlink()})
                except OSError:
                    continue

        visit(self.root / "config", Path("config"), frozenset())
        return result

    @staticmethod
    def _version(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def read(self, relative: str) -> WorkspaceFile:
        logical = self._path(relative)
        if not logical.is_file():
            raise FileNotFoundError(relative)
        content = logical.read_text(encoding="utf-8")
        return WorkspaceFile(relative, content, self._version(content), logical.is_symlink())

    def _validate(self, relative: str, content: str) -> None:
        path = self._path(relative)
        if not self._supported(path):
            raise ValueError("unsupported workspace file type")

    def write(self, relative: str, content: str, expected: str | None) -> WorkspaceFile:
        logical = self._path(relative)
        if logical.exists():
            current = self.read(relative)
            if expected is None or expected != current.version:
                raise WorkspaceConflict(current.version)
        elif expected not in {None, "*"}:
            raise WorkspaceConflict("missing")
        self._validate(relative, content)
        target = logical.resolve() if logical.is_symlink() else logical
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                os.chmod(temporary, 0o640)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.read(relative)

    def create_directory(self, relative: str) -> None:
        path = self._path(relative)
        if path.exists() or path.is_symlink():
            raise FileExistsError(relative)
        path.mkdir(parents=False)
        if os.name != "nt":
            path.chmod(0o750)

    def move(self, source: str, target: str) -> None:
        old, new = self._path(source), self._path(target)
        if not old.exists() and not old.is_symlink():
            raise FileNotFoundError(source)
        if new.exists() or new.is_symlink():
            raise FileExistsError(target)
        is_directory = old.is_dir()
        if not is_directory and not self._supported(new):
            raise ValueError("unsupported workspace file type")
        if is_directory and new.parts[: len(old.parts)] == old.parts:
            raise ValueError("directory cannot move inside itself")
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)

    def copy(self, source: str, target: str) -> None:
        old, new = self._path(source), self._path(target)
        if not old.exists() and not old.is_symlink():
            raise FileNotFoundError(source)
        if new.exists() or new.is_symlink():
            raise FileExistsError(target)
        is_directory = old.is_dir()
        if not is_directory and not self._supported(new):
            raise ValueError("unsupported workspace file type")
        if is_directory and new.parts[: len(old.parts)] == old.parts:
            raise ValueError("directory cannot copy inside itself")

        def create() -> None:
            new.parent.mkdir(parents=True, exist_ok=True)
            if old.is_symlink():
                new.symlink_to(os.readlink(old), target_is_directory=old.is_dir())
            elif old.is_dir():
                shutil.copytree(old, new, symlinks=True)
            else:
                shutil.copy2(old, new)

        create()

    def delete(self, relative: str) -> None:
        path = self._path(relative)
        if not path.exists() and not path.is_symlink():
            raise FileNotFoundError(relative)
        trash = path.parent / f".localflow-delete-{uuid.uuid4().hex}"
        path.rename(trash)
        if trash.is_symlink() or trash.is_file():
            trash.unlink()
        else:
            shutil.rmtree(trash)
