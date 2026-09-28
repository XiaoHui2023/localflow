from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from localflow.api import create_app
from localflow.executor import SubprocessExecutor
from localflow.models import TaskCreate
from localflow.plugins import PluginRegistry
from localflow.service import TaskService
from localflow.settings import (
    ExecutionSettings,
    LoggingSettings,
    ServerSettings,
    Settings,
    initialize_root,
)
from localflow.storage import Store


async def finish(service, store, task_id):
    await service.start()
    for _ in range(200):
        task = store.get_task(task_id)
        if task.ended_at:
            return task
        await asyncio.sleep(0.02)
    pytest.fail("task did not reach authoritative terminal state")


@pytest.mark.asyncio
@pytest.mark.parametrize("repeat", [0, 1])
async def test_generated_invalid_utf8_search_has_exact_byte_offsets(tmp_path: Path, repeat) -> None:
    store = Store(tmp_path / "runtime/localflow.db")
    service = TaskService(tmp_path, store, SubprocessExecutor(), max_concurrency=1)
    payload = b"\xff\xfe before needle\n" + b"x" * (1024 * 1024 - 3) + "中文 needle\n".encode()
    input_path = tmp_path / "input.bin"
    input_path.write_bytes(payload)
    task = service.submit(TaskCreate(
        name=f"byte-search-{repeat}", working_directory=str(tmp_path),
        command=[sys.executable, "-c", "import sys,pathlib;sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())", str(input_path)],
    ))
    try:
        await finish(service, store, task.id)
        data, _offset = service.read_log(task.id, 0, 1024 * 1024)
        path = tmp_path / "logs" / task.id / "output.log"
        full = path.read_bytes()
        assert b"\xff\xfe before needle" in data
        found = service.search_log(task.id, "needle")["items"]
        expected = [i for i in range(len(full)) if full.startswith(b"needle", i)]
        assert [item["offset"] for item in found] == expected
    finally:
        await service.stop()
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("repeat", [0, 1])
@pytest.mark.parametrize("change", ["update", "remove"])
async def test_changed_result_plugin_cannot_display_success(tmp_path: Path, repeat, change) -> None:
    directory = tmp_path / "plugins"
    directory.mkdir()
    plugin = directory / "evidence.py"
    source = (
        "from localflow.plugins import plugin\n"
        "from localflow.models import TaskDraft\n"
        "@plugin('evidence')\nclass Evidence:\n"
        " run_fields=[]\n"
        " statuses={'passed': {'label':'PASS','tone':'success','finished':True}}\n"
        " def expand(self, values, context): return [TaskDraft(**values)]\n"
        " def evaluate_result(self, task, context): return 'passed'\n"
    )
    plugin.write_text(source, encoding="utf-8")
    registry = PluginRegistry(directory)
    registry.load()
    assert not registry.diagnostics, registry.diagnostics
    drafts = registry.expand_config({
        "plugin": "evidence", "name": f"changed-plugin-{repeat}",
        "working_directory": str(tmp_path), "command": [sys.executable, "-c", "print('completed')"],
    }, {}, {"root": str(tmp_path)})
    store = Store(tmp_path / "runtime/localflow.db")
    service = TaskService(tmp_path, store, SubprocessExecutor(), max_concurrency=1,
                          result_evaluator=registry.evaluate_result)
    task = service.submit(drafts[0])
    if change == "update":
        plugin.write_text(source + "\n# legitimate plugin update after queue acceptance\n", encoding="utf-8")
    else:
        plugin.unlink()
    registry.load()
    if change == "remove":
        # Hot reload keeps the last good in-memory generation when every
        # plugin disappears. A restart has no such cached evaluator.
        restarted = PluginRegistry(directory)
        restarted.load()
        service = TaskService(tmp_path, store, SubprocessExecutor(), max_concurrency=1,
                              result_evaluator=restarted.evaluate_result)
    try:
        result = await finish(service, store, task.id)
        assert result.exit_code == 0
        assert result.state.value == "succeeded"  # Process outcome remains independent.
        assert result.status.key == "evaluation_error"
        assert result.status.tone == "danger"
        expected = "changed after task submission" if change == "update" else "unavailable"
        assert expected in result.custom["result_evaluation_error"]
    finally:
        await service.stop()
        store.close()


@pytest.mark.asyncio
async def test_plugin_success_cannot_hide_a_nonzero_process_exit(tmp_path: Path) -> None:
    from localflow.models import TaskStatus
    store = Store(tmp_path / "runtime/localflow.db")
    service = TaskService(tmp_path, store, SubprocessExecutor(), max_concurrency=1,
        result_evaluator=lambda _task, _context: (
            TaskStatus(key="passed", label="PASS", tone="success", finished=True), {"reported": "pass"}))
    task = service.submit(TaskCreate(name="contradiction", working_directory=str(tmp_path),
                                     command=[sys.executable, "-c", "raise SystemExit(7)"]))
    try:
        result = await finish(service, store, task.id)
        assert result.exit_code == 7 and result.state.value == "failed"
        assert result.status.key == "execution_failed" and result.status.tone == "danger"
        assert result.custom["reported_result_status"]["key"] == "passed"
    finally:
        await service.stop()
        store.close()


@pytest.mark.parametrize("repeat", [0, 1])
def test_public_task_exposes_output_loss(tmp_path: Path, repeat) -> None:
    app = create_app(tmp_path, settings=Settings(
        execution=ExecutionSettings(backend="subprocess", max_concurrency=1),
        server=ServerSettings(anonymous_access="readonly"),
        logging=LoggingSettings(task_file_mb=1, keep_free_mb=0),
    ))
    with TestClient(app) as client:
        key = (tmp_path / "secrets/web-admin-key").read_text().strip()
        login = client.post("/api/v1/auth/local-sessions", json={"key": key}).json()
        client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": login["csrf_token"]})
        response = client.post("/api/v1/tasks", json={
            "name": f"capped-{repeat}", "working_directory": str(tmp_path),
            "command": [sys.executable, "-c", "print('x' * 1500000);print('DECISIVE-END')"],
        })
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        import time
        for _ in range(200):
            detail = client.get(f"/api/v1/tasks/{task_id}").json()
            if detail["ended_at"]:
                break
            time.sleep(0.02)
        assert detail["exit_code"] == 0
        assert detail["output_integrity"]["complete"] is False
        assert detail["output_integrity"]["reason"] == "file_limit"
        assert detail["log_size"] <= 1024 * 1024


@pytest.mark.asyncio
@pytest.mark.parametrize("repeat", [0, 1])
async def test_public_verification_cannot_hide_failure_in_another_file(tmp_path: Path, repeat) -> None:
    initialize_root(tmp_path)
    registry = PluginRegistry(tmp_path / "plugins")
    registry.load()
    first, second = tmp_path / "first.log", tmp_path / "second.log"
    clean = "UVM Report Summary\nUVM_ERROR : 0\nUVM_FATAL : 0\n"
    bad = "UVM Report Summary\nUVM_ERROR : 3\nUVM_FATAL : 0\n"
    code = f"from pathlib import Path;Path({str(first)!r}).write_text({bad!r});Path({str(second)!r}).write_text({clean!r})"
    draft = registry.expand_config({
        "plugin": "verification", "case_names": ["case-a"],
        "working_directory": str(tmp_path), "command": [sys.executable, "-c", code],
        "run_logs": [str(first), str(second)],
    }, {"cases": ["case-a"], "seed": 1}, {"root": str(tmp_path)})[0]
    store = Store(tmp_path / "runtime/localflow.db")
    service = TaskService(tmp_path, store, SubprocessExecutor(), max_concurrency=1,
                          result_evaluator=registry.evaluate_result)
    task = service.submit(draft)
    try:
        result = await finish(service, store, task.id)
        assert result.exit_code == 0
        assert result.status.key == "error"
        assert result.custom["运行日志"] == [str(first), str(second)]
    finally:
        await service.stop()
        store.close()
