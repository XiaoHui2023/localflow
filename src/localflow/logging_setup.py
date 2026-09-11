from __future__ import annotations

import logging
import re
import shutil
import sys
from contextlib import suppress
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .log_files import MIB
from .settings import LoggingSettings

_AUTHORIZATION = re.compile(
    r"(?i)\b(authorization)(\s*[=:]\s*)(?:bearer\s+)?([^\s,;]+)"
)
_SENSITIVE = re.compile(r"(?i)\b(api[-_ ]?key|password|secret|token)(\s*[=:]\s*)([^\s,;]+)")


class _ExactDebug(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == logging.DEBUG


class _Redact(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        rendered = _AUTHORIZATION.sub(r"\1\2[redacted]", rendered)
        record.msg = _SENSITIVE.sub(r"\1\2[redacted]", rendered)
        record.args = ()
        return True


class _RoutineNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if record.name == "watchfiles.main" and "rust notify timeout" in message:
            return False
        return not (
            record.name == "uvicorn.access"
            and (
                '"GET /api/v1/system/status ' in message
                or '"GET /api/v1/tasks?limit=200 ' in message
            )
        )


class _ReservedSpaceRotatingHandler(RotatingFileHandler):
    def __init__(self, *args: object, keep_free_bytes: int, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.keep_free_bytes = keep_free_bytes
        self._warned = False
        self._storage_warned = False

    def _report_storage_error(self) -> None:
        if self._storage_warned:
            return
        with suppress(OSError):
            sys.stderr.write(
                "LocalFlow file logging paused: service log directory is unavailable; "
                "console logging remains active.\n"
            )
        self._storage_warned = True

    def _prepare_destination(self) -> Path:
        destination = Path(self.baseFilename)
        parent = destination.parent
        parent_was_missing = not parent.is_dir()
        if parent_was_missing:
            parent.mkdir(parents=True, exist_ok=True)
            if sys.platform != "win32":
                parent.chmod(0o750)
        if parent_was_missing and self.stream is not None and not destination.is_file():
            self.stream.close()
            self.stream = None
        return parent

    def handleError(self, record: logging.LogRecord) -> None:
        if isinstance(sys.exc_info()[1], OSError):
            if self.stream is not None:
                with suppress(OSError):
                    self.stream.close()
                self.stream = None
            self._report_storage_error()
            return
        super().handleError(record)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            parent = self._prepare_destination()
            if (
                self.keep_free_bytes
                and shutil.disk_usage(parent).free <= self.keep_free_bytes
            ):
                if not self._warned:
                    sys.stderr.write(
                        "LocalFlow file logging paused: free-space reserve reached.\n"
                    )
                    self._warned = True
                return
            self._warned = False
            super().emit(record)
            if self.stream is not None:
                self._storage_warned = False
        except OSError:
            self.handleError(record)


def configure_logging(root: Path, settings: LoggingSettings) -> None:
    log_root = root / "logs" / "service"
    log_root.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        log_root.chmod(0o750)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in list(root_logger.handlers):
        if getattr(handler, "_localflow_handler", False):
            root_logger.removeHandler(handler)
            handler.close()

    redactor = _Redact()
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, settings.level.upper()))
    console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    console.addFilter(redactor)

    common = {
        "maxBytes": settings.service_file_mb * MIB,
        "backupCount": settings.service_files,
        "encoding": "utf-8",
        "delay": True,
        "keep_free_bytes": settings.keep_free_mb * MIB,
    }
    service = _ReservedSpaceRotatingHandler(log_root / "service.log", **common)
    service.setLevel(logging.INFO)
    service.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    service.addFilter(_RoutineNoise())
    service.addFilter(redactor)

    debug = _ReservedSpaceRotatingHandler(log_root / "debug.log", **common)
    debug.setLevel(logging.DEBUG)
    debug.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    debug.addFilter(_ExactDebug())
    debug.addFilter(_RoutineNoise())
    debug.addFilter(redactor)

    for handler in (console, service, debug):
        handler._localflow_handler = True  # type: ignore[attr-defined]
        root_logger.addHandler(handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
