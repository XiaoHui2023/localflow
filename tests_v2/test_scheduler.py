from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from localflow.executor import SubprocessExecutor
from localflow.models import StopAction, StopStrategy, TaskCreate
from localflow.plugins import PluginRegistry
from localflow.service import TaskService
from localflow.settings import initialize_root
from localflow.storage import Store


class FlakyWaitExecutor(SubprocessExecutor):
    """Inject one result-channel failure while leaving the owned process alive."""

    def __init__(self) -> None:
        super().__init__()
        self.wait_attempts = 0

    async def wait(self, task_id: str) -> int:
        self.wait_attempts += 1
        if self.wait_attempts == 1:
            await asyncio.sleep(0.03)
            raise RuntimeError("injected transient wait failure")
        return await super().wait(task_id)


class DelayedStartExecutor(SubprocessExecutor):
    """Hold launch ownership transfer open to exercise controller shutdown."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def start(self, task, log_path):
        self.entered.set()
        await self.release.wait()
        return await super().start(task, log_path)


@pytest.mark.asyncio
async def test_mutex_queue_and_logs(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=2)
    command = [sys.executable, "-c", "import time; print('ok', flush=True); time.sleep(.15)"]
    first = service.submit(
        TaskCreate(
            name="one", working_directory=str(root), command=command, mutex_keys=["license:a"]
        )
    )
    second = service.submit(
        TaskCreate(
            name="two", working_directory=str(root), command=command, mutex_keys=["license:a"]
        )
    )
    third = service.submit(
        TaskCreate(
            name="three", working_directory=str(root), command=command, mutex_keys=["license:b"]
        )
    )
    queued_log = root / "logs" / first.id / "output.log"
    assert queued_log.is_file()
    assert b"task.queued" in queued_log.read_bytes()
    await service.start()
    for _ in range(50):
        await asyncio.sleep(0.01)
        queued = store.get_task(second.id)
        if queued.state == "queued" and queued.blocked_by:
            break
    assert store.get_task(second.id).blocked_by == [first.id]
    assert store.get_task(second.id).blocked_keys == ["license:a"]
    for _ in range(100):
        await asyncio.sleep(0.03)
        if all(store.get_task(item.id).ended_at for item in (first, second, third)):
            break
    await service.stop()
    one, two, three = [store.get_task(item.id) for item in (first, second, third)]
    assert one.state == two.state == three.state == "succeeded"
    assert two.started_at >= one.ended_at
    task_log = service.read_log(first.id)[0]
    assert b"task.starting" in task_log
    assert b"process.started" in task_log
    assert b"process.command" in task_log
    assert b"ok" in task_log
    assert b"process.exited" in task_log
    store.close()


@pytest.mark.asyncio
async def test_subprocess_relative_side_effect_stays_in_configured_workdir(
    root: Path,
) -> None:
    root.mkdir()
    project = root.parent / "external-project"
    project.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="cwd-side-effect",
            working_directory=str(project),
            command=[
                sys.executable,
                "-c",
                "from pathlib import Path; Path('generated').mkdir(); "
                "Path('generated/marker.txt').write_text(str(Path.cwd()))",
            ],
        )
    )
    await service.start()
    try:
        for _ in range(100):
            await asyncio.sleep(0.02)
            if store.get_task(task.id).ended_at:
                break
        assert store.get_task(task.id).state == "succeeded"
        marker = project / "generated" / "marker.txt"
        assert marker.read_text(encoding="utf-8") == str(project)
        assert not (root / "generated").exists()
    finally:
        await service.stop()
        store.close()


@pytest.mark.asyncio
async def test_transient_wait_failure_never_marks_a_live_process_terminal(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    executor = FlakyWaitExecutor()
    service = TaskService(root, store, executor, max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="wait-retry",
            working_directory=str(root),
            command=[sys.executable, "-c", "import time; time.sleep(.15)"],
        )
    )
    await service.start()
    try:
        for _ in range(100):
            await asyncio.sleep(0.02)
            if store.get_task(task.id).ended_at:
                break
        result = store.get_task(task.id)
        assert executor.wait_attempts >= 2
        assert result.state == "succeeded"
        assert result.exit_code == 0
    finally:
        await service.stop()
        store.close()


@pytest.mark.asyncio
async def test_shutdown_waits_for_inflight_launch_then_cleans_process_group(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    executor = DelayedStartExecutor()
    service = TaskService(root, store, executor, max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="inflight-launch",
            working_directory=str(root),
            command=[sys.executable, "-c", "import time; time.sleep(30)"],
        )
    )
    await service.start()
    try:
        await asyncio.wait_for(executor.entered.wait(), timeout=1)
        shutdown = asyncio.create_task(service.shutdown_all(timeout_seconds=0.05))
        await asyncio.sleep(0.02)
        assert not shutdown.done()
        executor.release.set()
        await asyncio.wait_for(shutdown, timeout=3)
        result = store.get_task(task.id)
        assert result.state == "cancelled"
        assert result.interrupt_stage in {"stop:0:signal", "sigkill"}
        assert not await executor.is_running(result)
    finally:
        executor.release.set()
        await service.stop()
        store.close()


@pytest.mark.asyncio
async def test_start_failure_keeps_time_and_complete_diagnostic_log(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    missing = root / "missing-working-directory"
    task = service.submit(
        TaskCreate(
            name="broken-start",
            working_directory=str(missing),
            command=[sys.executable, "-c", "print('must not run')"],
        )
    )
    output = root / "logs" / task.id / "output.log"
    assert output.is_file()
    await service.start()
    try:
        for _ in range(100):
            current = store.get_task(task.id)
            if current.ended_at:
                break
            await asyncio.sleep(0.02)
        current = store.get_task(task.id)
        assert current.state.value == "failed"
        assert current.started_at is not None
        assert current.ended_at is not None
        assert current.elapsed_seconds is not None
        assert current.log_size == output.stat().st_size > 0
        text = output.read_text(encoding="utf-8")
        assert "task.queued" in text
        assert missing.name in text
        assert "task.starting" in text
        assert "executor.start_failed" in text
        assert "working directory does not exist" in text
        assert "task.start_failed" in text
    finally:
        await service.stop()
        store.close()


@pytest.mark.asyncio
async def test_interrupt_starts_with_sigint(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="long",
            working_directory=str(root),
            command=[sys.executable, "-c", "import time; time.sleep(30)"],
        )
    )
    await service.start()
    for _ in range(50):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).state == "running":
            break
    await service.interrupt(task.id, 0.05, 0.05)
    for _ in range(100):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    assert result.state == "cancelled"
    assert result.interrupt_stage in {"stop:0:signal", "stop:1:signal"}
    assert [action.timeout_seconds for action in result.stop.actions] == [0.05, 0.05]
    await service.stop()
    store.close()


@pytest.mark.asyncio
async def test_custom_stop_inputs_follow_new_output_and_cancel_clean_exit(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    script = (
        "import sys\n"
        "for line in sys.stdin:\n"
        " print('prompt: quit', flush=True) if line.strip() == 'prepare' else None\n"
        " if line.strip() == 'quit': raise SystemExit(0)\n"
    )
    task = service.submit(
        TaskCreate(
            name="interactive-stop",
            working_directory=str(root),
            command=[sys.executable, "-u", "-c", script],
            stop=StopStrategy(
                actions=[
                    StopAction(
                        type="input",
                        data="prepare\n",
                        output_contains="prompt: quit",
                        timeout_seconds=2,
                    ),
                    StopAction(type="input", data="quit\n", timeout_seconds=2),
                ]
            ),
        )
    )
    await service.start()
    for _ in range(50):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).state == "running":
            break
    await service.interrupt(task.id)
    for _ in range(150):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    assert result.state == "cancelled"
    assert result.exit_code == 0
    assert result.interrupt_stage == "stop:1:input"
    assert b"prompt: quit" in service.read_log(task.id)[0]
    await service.stop()
    store.close()


@pytest.mark.asyncio
async def test_second_interrupt_click_advances_current_wait(root: Path) -> None:
    root.mkdir()
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="advance-stop",
            working_directory=str(root),
            command=[
                sys.executable,
                "-u",
                "-c",
                "import sys\nfor line in sys.stdin:\n if line.strip() == 'quit': raise SystemExit(0)",
            ],
            stop=StopStrategy(
                actions=[
                    StopAction(type="input", data="wait\n", timeout_seconds=30),
                    StopAction(type="input", data="quit\n", timeout_seconds=2),
                ]
            ),
        )
    )
    await service.start()
    for _ in range(50):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).state == "running":
            break
    await service.interrupt(task.id)
    assert store.get_task(task.id).state == "stopping"
    await asyncio.sleep(0.1)
    await service.interrupt(task.id)
    for _ in range(100):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).ended_at:
            break
    assert store.get_task(task.id).state == "cancelled"
    await service.stop()
    store.close()


def test_stop_progress_extension_requires_a_bounded_hard_deadline() -> None:
    action = StopAction(
        type="signal",
        signal="SIGINT",
        timeout_seconds=2,
        extend_timeout_on_output=True,
        max_timeout_seconds=30,
    )
    assert action.extend_timeout_on_output is True
    assert action.max_timeout_seconds == 30

    with pytest.raises(ValueError, match="max_timeout_seconds"):
        StopAction(
            type="signal",
            signal="SIGINT",
            timeout_seconds=2,
            extend_timeout_on_output=True,
        )
    with pytest.raises(ValueError, match="at least timeout_seconds"):
        StopAction(
            type="signal",
            signal="SIGINT",
            timeout_seconds=2,
            extend_timeout_on_output=True,
            max_timeout_seconds=1,
        )


@pytest.mark.asyncio
async def test_verification_result_is_frozen_from_run_log(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    compile_log = root / "artifacts" / "case-a.compile.log"
    run_log = root / "artifacts" / "case-a.run.log"
    document = {
        "plugin": "verification",
        "case_directory": str(root / "cases"),
        "working_directory": ".",
        "command": [
            sys.executable,
            "-u",
            str(root / "scripts" / "simulate.py"),
            "--case",
            "${case}",
            "--seed",
            "${seed}",
            "--compile-log",
            str(compile_log),
            "--run-log",
            str(run_log),
        ],
        "compile_logs": [str(compile_log)],
        "run_logs": [str(run_log)],
        "labels": ["nightly"],
        "custom_texts": ["Case: ${case}", "Seed: ${seed}"],
    }
    draft = registry.expand_config(document, {"cases": ["case-a"], "seed": 1}, {"root": str(root)})[
        0
    ]
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(
        root,
        store,
        SubprocessExecutor(),
        max_concurrency=1,
        result_evaluator=registry.evaluate_result,
    )
    task = service.submit(draft)
    await service.start()
    for _ in range(150):
        await asyncio.sleep(0.02)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    assert result.status.key == "error"
    assert result.status.label == "ERROR"
    assert result.custom == {
        "seed": 1,
        "自定义文本": ["Case: case-a", "Seed: 1"],
        "运行日志": [str(run_log)],
    }
    assert len(result.mutex_keys) == 1
    assert result.mutex_keys[0].startswith("verification:")
    await service.stop()
    store.close()


@pytest.mark.asyncio
async def test_automatic_verification_seeds_are_frozen_unique_and_persistent(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    document = {
        "plugin": "verification",
        "case_directory": str(root / "cases"),
        "working_directory": ".",
        "command": [
            sys.executable,
            "-c",
            "import sys; print(sys.argv[-1])",
            "--case",
            "${case}",
            "--seed",
            "${seed}",
        ],
        "labels": ["auto-seed"],
    }
    drafts = registry.expand_config(
        document,
        {"cases": ["case-a"], "case_runs": {"case-a": 3}, "seed": ""},
        {"root": str(root)},
    )
    assert all("seed" not in draft.custom for draft in drafts)
    assert all(draft.command[-1] == "${seed}" for draft in drafts)
    monkeypatch.setattr("localflow.storage.time.time", lambda: 1_700_000_000)
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(
        root,
        store,
        SubprocessExecutor(),
        max_concurrency=1,
        result_evaluator=registry.evaluate_result,
    )
    _batch_id, records = service.submit_batch("verification", {}, drafts)
    assert [record.custom["seed"] for record in records] == [
        1_700_000_000,
        1_700_000_001,
        1_700_000_002,
    ]
    assert [record.command[-1] for record in records] == [
        "1700000000",
        "1700000001",
        "1700000002",
    ]
    store.close()
    # A restarted host must keep allocating forward even if its wall clock moved back.
    monkeypatch.setattr("localflow.storage.time.time", lambda: 1_600_000_000)
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    next_draft = registry.expand_config(
        document, {"cases": ["case-a"], "seed": None}, {"root": str(root)}
    )[0]
    next_record = service.submit(next_draft)
    assert next_record.custom["seed"] == 1_700_000_003
    assert next_record.command[-1] == "1700000003"
    store.close()
