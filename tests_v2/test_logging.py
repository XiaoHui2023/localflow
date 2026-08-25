from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from collections import namedtuple
from pathlib import Path

import pytest

from localflow.executor import SubprocessExecutor
from localflow.log_files import OUTPUT_LIMIT_MARKER, BoundedLogWriter
from localflow.logging_setup import configure_logging
from localflow.models import TaskCreate
from localflow.service import TaskService
from localflow.settings import LoggingSettings
from localflow.storage import Store


def _remove_localflow_handlers() -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if getattr(handler, "_localflow_handler", False):
            root_logger.removeHandler(handler)
            handler.close()


def test_service_logs_are_rotated_split_and_redacted(root: Path) -> None:
    configure_logging(
        root,
        LoggingSettings(
            level="error",
            service_file_mb=1,
            service_files=2,
            keep_free_mb=0,
        ),
    )
    logger = logging.getLogger("localflow.test")
    try:
        logger.info("started api_key=do-not-store Authorization: Bearer header-secret")
        logger.debug("route token=also-secret")
        logging.getLogger("watchfiles.main").debug("rust notify timeout, continuing")
        logging.getLogger("uvicorn.access").info(
            '127.0.0.1 - "GET /api/v1/system/status HTTP/1.1" 200'
        )
        for index in range(20):
            logger.info("chunk=%s %s", index, "x" * 65536)
    finally:
        _remove_localflow_handlers()

    service_logs = sorted((root / "logs" / "service").glob("service.log*"))
    debug_log = root / "logs" / "service" / "debug.log"
    assert 1 < len(service_logs) <= 3
    assert max(path.stat().st_size for path in service_logs) < 1100000
    service_text = "".join(path.read_text(encoding="utf-8") for path in service_logs)
    debug_text = debug_log.read_text(encoding="utf-8")
    assert "do-not-store" not in service_text
    assert "header-secret" not in service_text
    assert "started api_key=[redacted]" in service_text
    assert "also-secret" not in debug_text
    assert "route token=[redacted]" in debug_text
    assert "route token" not in service_text
    assert "rust notify timeout" not in debug_text
    assert "/api/v1/system/status" not in service_text


def test_task_output_has_hard_cap_and_keeps_task_running(tmp_path: Path) -> None:
    path = tmp_path / "output.log"
    with BoundedLogWriter(path, 1024) as writer:
        assert writer.write(b"a" * 4096) == 4096
        assert writer.write(b"b" * 4096) == 4096
    assert path.stat().st_size <= 1024
    assert path.read_bytes().endswith(OUTPUT_LIMIT_MARKER)


def test_task_output_pauses_at_free_space_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage(1000, 950, 50))
    path = tmp_path / "output.log"
    with BoundedLogWriter(path, 1024, keep_free_bytes=100) as writer:
        assert writer.write(b"still-consumed") == len(b"still-consumed")
    assert path.read_bytes() == b""


@pytest.mark.asyncio
async def test_subprocess_output_cap_does_not_kill_command(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    executor = SubprocessExecutor(task_log_max_bytes=4096)
    service = TaskService(root, store, executor, max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="chatty",
            working_directory=str(root),
            command=[sys.executable, "-c", "print('x' * 20000)"],
        )
    )
    await service.start()
    try:
        for _ in range(100):
            current = store.get_task(task.id)
            if current.ended_at is not None:
                break
            await asyncio.sleep(0.02)
        current = store.get_task(task.id)
        assert current.state.value == "succeeded"
        output = root / "logs" / task.id / "output.log"
        assert output.stat().st_size <= 4096
        assert output.read_bytes().endswith(OUTPUT_LIMIT_MARKER)
    finally:
        await service.stop()
        store.close()


def test_sqlite_database_and_wal_have_configured_caps(tmp_path: Path) -> None:
    store = Store(
        tmp_path / "runtime" / "localflow.db",
        database_max_bytes=16 * 1024 * 1024,
        wal_max_bytes=2 * 1024 * 1024,
    )
    try:
        page_size = int(store._db.execute("PRAGMA page_size").fetchone()[0])
        max_pages = int(store._db.execute("PRAGMA max_page_count").fetchone()[0])
        wal_limit = int(store._db.execute("PRAGMA journal_size_limit").fetchone()[0])
        assert max_pages * page_size <= 16 * 1024 * 1024
        assert wal_limit == 2 * 1024 * 1024
    finally:
        store.close()
