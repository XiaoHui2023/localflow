from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import BinaryIO

MIB = 1024 * 1024
OUTPUT_LIMIT_MARKER = b"\r\n[LocalFlow] task output limit reached; later output is not stored.\r\n"


class BoundedLogWriter:
    """Consume a byte stream while keeping its on-disk file strictly bounded."""

    def __init__(self, path: Path, max_bytes: int, keep_free_bytes: int = 0) -> None:
        if max_bytes <= len(OUTPUT_LIMIT_MARKER):
            raise ValueError("max_bytes is too small for a bounded task log")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.max_bytes = max_bytes
        self.keep_free_bytes = max(keep_free_bytes, 0)
        self._stream: BinaryIO = path.open("ab", buffering=0)
        self._size = path.stat().st_size
        self._stopped = self._size >= max_bytes
        self._bytes_since_space_check = MIB
        self._lock = threading.Lock()

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
                    self._stopped = True
                    return consumed
            payload_limit = self.max_bytes - len(OUTPUT_LIMIT_MARKER)
            if self._size + len(data) <= payload_limit:
                self._stream.write(data)
                self._size += len(data)
                return consumed
            remaining = max(payload_limit - self._size, 0)
            if remaining:
                self._stream.write(data[:remaining])
                self._size += remaining
            self._stream.write(OUTPUT_LIMIT_MARKER)
            self._size += len(OUTPUT_LIMIT_MARKER)
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
