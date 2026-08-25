from __future__ import annotations

import logging
import re
import shutil
import sys
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

    def emit(self, record: logging.LogRecord) -> None:
        if (
            self.keep_free_bytes
            and shutil.disk_usage(Path(self.baseFilename).parent).free <= self.keep_free_bytes
        ):
            if not self._warned:
                sys.stderr.write("LocalFlow file logging paused: free-space reserve reached.\n")
                self._warned = True
            return
        self._warned = False
        super().emit(record)


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
