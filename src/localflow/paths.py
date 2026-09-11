from __future__ import annotations

import json
import os
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

STATE_FORMAT_VERSION = 1
STATE_MARKER = ".localflow-state.json"


class StateCompatibilityError(RuntimeError):
    """The selected state directory belongs to an unsupported newer LocalFlow."""


@dataclass(frozen=True)
class LocalFlowPaths:
    """Paths grouped by owner and lifetime rather than by file type."""

    config_root: Path
    state_root: Path

    @classmethod
    def resolve(
        cls,
        *,
        startup_directory: Path,
        config_root: Path | None = None,
        state_root: Path | None = None,
    ) -> LocalFlowPaths:
        startup = startup_directory.resolve()
        configuration = _resolve_from(startup, config_root or Path("."))
        state = _resolve_from(startup, state_root or Path(".localflow"))
        return cls(configuration, state)


def _resolve_from(base: Path, candidate: Path) -> Path:
    return (candidate if candidate.is_absolute() else base / candidate).resolve()


def initialize_state_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / STATE_MARKER
    instance_id: str | None = None
    if marker.exists():
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            version = int(payload["format"])
            candidate_id = payload.get("instance_id")
            if isinstance(candidate_id, str) and candidate_id:
                instance_id = candidate_id
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            _quarantine_dynamic_state(root, "invalid-marker")
        else:
            if version > STATE_FORMAT_VERSION:
                raise StateCompatibilityError(
                    f"state directory format {version} is newer than supported format "
                    f"{STATE_FORMAT_VERSION}: {root}"
                )
            if version < STATE_FORMAT_VERSION:
                _quarantine_dynamic_state(root, f"format-{version}")
    _create_state_directories(root)
    if not marker.exists() or instance_id is None:
        _write_state_marker(marker, instance_id or secrets.token_hex(16))


def _write_state_marker(marker: Path, instance_id: str) -> None:
    temporary = marker.with_name(
        f".{marker.name}.{os.getpid()}.{secrets.token_hex(8)}.new"
    )
    temporary.write_text(
        json.dumps(
            {"format": STATE_FORMAT_VERSION, "instance_id": instance_id},
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        os.chmod(temporary, 0o600)
    os.replace(temporary, marker)


def state_instance_id(root: Path) -> str:
    payload = json.loads((root / STATE_MARKER).read_text(encoding="utf-8"))
    value = payload.get("instance_id")
    if not isinstance(value, str) or not value:
        raise StateCompatibilityError(f"state directory has no instance identity: {root}")
    return value


def validate_state_root(root: Path) -> None:
    """Reject a known newer format without creating even the instance lock file."""
    marker = root / STATE_MARKER
    if not marker.exists():
        return
    try:
        version = int(json.loads(marker.read_text(encoding="utf-8"))["format"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return
    if version > STATE_FORMAT_VERSION:
        raise StateCompatibilityError(
            f"state directory format {version} is newer than supported format "
            f"{STATE_FORMAT_VERSION}: {root}"
        )


def _create_state_directories(root: Path) -> None:
    for relative in ("runtime/instances", "logs/service", "exports", "cache", "recovery"):
        path = root / relative
        created = not path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if created and os.name != "nt":
            os.chmod(path, 0o750)


def _quarantine_dynamic_state(root: Path, reason: str) -> None:
    stamp = f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{time.time_ns()}"
    recovery = root / "recovery" / f"{stamp}-{reason}"
    recovery.mkdir(parents=True, exist_ok=False)
    for name in ("runtime", "logs", "exports", "cache"):
        source = root / name
        if source.exists() or source.is_symlink():
            shutil.move(str(source), recovery / name)
    (root / STATE_MARKER).unlink(missing_ok=True)


class InstanceLock:
    """Hold an advisory, process-lifetime lock for one service state directory."""

    def __init__(self, state_root: Path) -> None:
        self.path = state_root / ".instance.lock"
        self._stream = None

    def __enter__(self) -> InstanceLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise RuntimeError(f"state directory is already in use: {self.path.parent}") from exc
        self._stream = stream
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        if self._stream is None:
            return
        if os.name == "nt":
            import msvcrt

            self._stream.seek(0)
            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        self._stream.close()
        self._stream = None
