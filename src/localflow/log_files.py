from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

MIB = 1024 * 1024
OUTPUT_LIMIT_MARKER = b"\r\n[LocalFlow] task output limit reached; later output is not stored.\r\n"
logger = logging.getLogger(__name__)


def output_integrity(path: Path) -> dict[str, object]:
    """Read durable capture health without loading the task archive."""
    metadata = path.with_suffix(path.suffix + ".integrity.json")
    if not path.is_file():
        return {"complete": False, "reason": "missing"}
    try:
        with metadata.open("rb") as stream:
            value = json.loads(stream.read(1024))
        if (not isinstance(value, dict) or "complete" not in value
                or (value["complete"] is not None and not isinstance(value["complete"], bool))):
            raise ValueError("invalid integrity metadata")
        return value
    except FileNotFoundError:
        try:
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - len(OUTPUT_LIMIT_MARKER)))
                if stream.read() == OUTPUT_LIMIT_MARKER:
                    return {"complete": False, "reason": "file_limit"}
        except FileNotFoundError:
            return {"complete": False, "reason": "missing"}
        return {"complete": None, "reason": "legacy_unverified"}
    except (OSError, ValueError):
        return {"complete": None, "reason": "metadata_unreadable"}


def lifecycle_line(event: str, **fields: object) -> bytes:
    """Create a compact, human-readable task lifecycle record."""

    timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
    details = " ".join(f"{key}={value!r}" for key, value in fields.items() if value is not None)
    suffix = f" {details}" if details else ""
    return f"[LocalFlow {timestamp}] {event}{suffix}\n".encode("utf-8", errors="replace")


def append_lifecycle(
    path: Path,
    max_bytes: int,
    keep_free_bytes: int,
    event: str,
    **fields: object,
) -> None:
    """Append a bounded lifecycle record and make the task log exist immediately."""

    with BoundedLogWriter(path, max_bytes, keep_free_bytes) as writer:
        writer.write(lifecycle_line(event, **fields))


class BoundedLogWriter:
    """Consume a byte stream while keeping its on-disk file strictly bounded."""

    def __init__(self, path: Path, max_bytes: int, keep_free_bytes: int = 0) -> None:
        if max_bytes != 0 and max_bytes <= len(OUTPUT_LIMIT_MARKER):
            raise ValueError("max_bytes is too small for a bounded task log")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.max_bytes = max_bytes
        self.keep_free_bytes = max(keep_free_bytes, 0)
        self._stream: BinaryIO = path.open("ab", buffering=0)
        self._size = path.stat().st_size
        self._metadata = path.with_suffix(path.suffix + ".integrity.json")
        # Reserve a small existing allocation while storage is still healthy.
        # Later disk-reserve notifications need no new file allocation.
        if not self._metadata.exists():
            self._metadata.write_bytes(
                json.dumps({"complete": True if self._size == 0 else None, "reason": (
                    None if self._size == 0 else "legacy_unverified"
                )}).encode().ljust(1024, b" ")
            )
        health = output_integrity(path)
        self._stopped = health.get("reason") in {"file_limit", "disk_reserve", "write_error"}
        if max_bytes and self._size >= max_bytes:
            self._stopped = True
            self._mark_incomplete("file_limit")
        self._bytes_since_space_check = MIB
        self._lock = threading.Lock()

    def _mark_incomplete(self, reason: str) -> None:
        self._stopped = True
        payload = json.dumps({"complete": False, "reason": reason}).encode().ljust(1024, b" ")
        try:
            with self._metadata.open("r+b", buffering=0) as stream:
                stream.write(payload)
        except OSError:
            # Metadata reads fail closed; never reinterpret a broken receipt
            # as a complete archive. Keep a second, observable service error.
            logger.exception("task output integrity record unavailable path=%s", self.path)
            try:
                self._metadata.unlink(missing_ok=True)
            except OSError:
                logger.exception("stale integrity record could not be removed path=%s", self.path)
        logger.error("task output capture incomplete path=%s reason=%s", self.path, reason)

    def _append(self, data: bytes) -> bool:
        try:
            view = memoryview(data)
            while view:
                size = self._stream.write(view)
                if not size:
                    raise OSError("task log write made no progress")
                self._size += size
                view = view[size:]
            return True
        except OSError:
            self._mark_incomplete("write_error")
            return False

    def write(self, data: bytes) -> int:
        consumed = len(data)
        if not data:
            return 0
        with self._lock:
            if self._stopped:
                return consumed
            self._bytes_since_space_check += len(data)
            if self._bytes_since_space_check >= MIB:
                self._bytes_since_space_check = 0
                if (
                    self.keep_free_bytes
                    and shutil.disk_usage(self.path.parent).free <= self.keep_free_bytes
                ):
                    self._mark_incomplete("disk_reserve")
                    return consumed
            if self.max_bytes == 0:
                self._append(data)
                return consumed
            payload_limit = self.max_bytes - len(OUTPUT_LIMIT_MARKER)
            if self._size + len(data) <= payload_limit:
                self._append(data)
                return consumed
            remaining = max(payload_limit - self._size, 0)
            self._mark_incomplete("file_limit")
            if remaining and not self._append(data[:remaining]):
                return consumed
            self._append(OUTPUT_LIMIT_MARKER)
            self._stopped = True
            return consumed

    def close(self) -> None:
        with self._lock:
            if not self._stream.closed:
                self._stream.close()

    def __enter__(self) -> BoundedLogWriter:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
