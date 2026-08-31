from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from localflow.control import control_socket_path
from localflow.executor import SystemdExecutor
from localflow.models import StopAction, StopStrategy, TaskCreate
from localflow.service import TaskService
from localflow.settings import initialize_root
from localflow.storage import Store


@pytest.mark.asyncio
async def test_real_systemd_executor_success_and_pty_log(tmp_path: Path) -> None:
    root = tmp_path / "localflow-root"
    initialize_root(root)
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SystemdExecutor(root), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="systemd-success",
            working_directory=str(root),
            command=["/bin/sh", "-c", "printf systemd-pty-ok"],
        )
    )
    await service.start()
    for _ in range(100):
        await asyncio.sleep(0.05)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    assert result.state == "succeeded"
    assert result.executor_ref == f"localflow-task-{task.id}.service"
    assert b"systemd-pty-ok" in service.read_log(task.id)[0]
    await service.stop()
    store.close()


@pytest.mark.asyncio
async def test_real_systemd_executor_runs_make_variables_and_logs_command(
    tmp_path: Path,
) -> None:
    root = tmp_path / "localflow-make"
    initialize_root(root)
    project = tmp_path / "simulation-project"
    project.mkdir()
    (project / "Makefile").write_text(
        ".PHONY: all\nall:\n\t@printf 'cwd=%s case=%s seed=%s' \"$$PWD\" \"$(CASE)\" \"$(SEED)\"\n",
        encoding="utf-8",
    )
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SystemdExecutor(root), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="make-contract",
            working_directory=str(project),
            command="make all CASE=case-a SEED=12345",
        )
    )
    await service.start()
    for _ in range(200):
        await asyncio.sleep(0.05)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    output = service.read_log(task.id)[0]
    assert result.state == "succeeded"
    assert f"cwd='{project}'".encode() in output
    assert b"command='make all CASE=case-a SEED=12345'" in output
    assert f"cwd={project}".encode() in output
    assert b"case=case-a seed=12345" in output
    await service.stop()
    store.close()


@pytest.mark.asyncio
async def test_real_systemd_executor_sigint_first(tmp_path: Path) -> None:
    root = tmp_path / "localflow-root"
    initialize_root(root)
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SystemdExecutor(root), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="systemd-interrupt",
            working_directory=str(root),
            command=[
                "/bin/sh",
                "-c",
                "trap 'printf got-sigint; exit 130' INT; while :; do sleep 1; done",
            ],
        )
    )
    await service.start()
    for _ in range(100):
        await asyncio.sleep(0.05)
        if control_socket_path(root, task.id).exists():
            break
    await service.interrupt(task.id, sigint_grace=1, sigterm_grace=1)
    for _ in range(100):
        await asyncio.sleep(0.05)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    assert result.state == "cancelled"
    assert result.interrupt_stage == "stop:0:signal"
    assert b"got-sigint" in service.read_log(task.id)[0]
    await service.stop()
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("program", "expected_stage"),
    [
        (
            "import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(143))); "
            "time.sleep(30)",
            "stop:1:signal",
        ),
        (
            "import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
            "sigkill",
        ),
    ],
)
async def test_real_systemd_interrupt_escalates(
    tmp_path: Path, program: str, expected_stage: str
) -> None:
    root = tmp_path / f"localflow-{expected_stage}"
    initialize_root(root)
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SystemdExecutor(root), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name=f"interrupt-{expected_stage}",
            working_directory=str(root),
            command=[sys.executable, "-c", program],
        )
    )
    await service.start()
    for _ in range(100):
        await asyncio.sleep(0.05)
        if control_socket_path(root, task.id).exists():
            break
    await service.interrupt(task.id, sigint_grace=0.3, sigterm_grace=0.3)
    for _ in range(100):
        await asyncio.sleep(0.05)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    assert result.state == "cancelled"
    assert result.interrupt_stage == expected_stage
    await service.stop()
    store.close()


@pytest.mark.asyncio
async def test_real_systemd_interactive_stop_and_cgroup_cleanup(tmp_path: Path) -> None:
    root = tmp_path / "localflow-interactive-cleanup"
    initialize_root(root)
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SystemdExecutor(root), max_concurrency=1)
    orphan_file = root / "orphan.pid"
    script = (
        "import os,signal,subprocess,sys,time\n"
        f"child=subprocess.Popen(['sleep','30']); open({str(orphan_file)!r},'w').write(str(child.pid))\n"
        "stopping=False\n"
        "def stop(*_):\n global stopping; stopping=True; print('type quit',flush=True)\n"
        "signal.signal(signal.SIGINT,stop)\n"
        "while True:\n"
        " if stopping and sys.stdin.readline().strip() == 'quit': raise SystemExit(0)\n"
        " time.sleep(.05)\n"
    )
    task = service.submit(
        TaskCreate(
            name="interactive-cleanup",
            working_directory=str(root),
            command=[sys.executable, "-u", "-c", script],
            stop=StopStrategy(
                actions=[
                    StopAction(
                        type="signal",
                        signal="SIGINT",
                        output_contains="type quit",
                        timeout_seconds=2,
                    ),
                    StopAction(type="input", data="quit\n", timeout_seconds=2),
                ]
            ),
        )
    )
    await service.start()
    for _ in range(100):
        await asyncio.sleep(0.05)
        if orphan_file.exists() and control_socket_path(root, task.id).exists():
            break
    orphan_pid = int(orphan_file.read_text(encoding="ascii"))
    await service.interrupt(task.id)
    for _ in range(150):
        await asyncio.sleep(0.05)
        if store.get_task(task.id).ended_at:
            break
    result = store.get_task(task.id)
    assert result.state == "cancelled"
    assert result.exit_code == 0
    assert b"type quit" in service.read_log(task.id)[0]
    with pytest.raises(ProcessLookupError):
        os.kill(orphan_pid, 0)
    await service.stop()
    store.close()


@pytest.mark.asyncio
async def test_task_survives_control_service_restart(tmp_path: Path) -> None:
    root = tmp_path / "localflow-root"
    initialize_root(root)
    store = Store(root / "runtime" / "localflow.db")
    first_service = TaskService(root, store, SystemdExecutor(root), max_concurrency=1)
    task = first_service.submit(
        TaskCreate(
            name="survive-restart",
            working_directory=str(root),
            command=["/bin/sh", "-c", "sleep 1; printf survived-restart"],
        )
    )
    await first_service.start()
    for _ in range(100):
        await asyncio.sleep(0.02)
        if control_socket_path(root, task.id).exists():
            break
    assert store.get_task(task.id).state == "running"
    await first_service.stop()
    store.close()

    recovered_store = Store(root / "runtime" / "localflow.db")
    recovered = TaskService(root, recovered_store, SystemdExecutor(root), max_concurrency=1)
    await recovered.start()
    for _ in range(150):
        await asyncio.sleep(0.03)
        if recovered_store.get_task(task.id).ended_at:
            break
    result = recovered_store.get_task(task.id)
    assert result.state == "succeeded"
    assert b"survived-restart" in recovered.read_log(task.id)[0]
    await recovered.stop()
    recovered_store.close()


@pytest.mark.asyncio
async def test_recover_exit_written_while_control_service_was_down(tmp_path: Path) -> None:
    root = tmp_path / "localflow-root"
    initialize_root(root)
    store = Store(root / "runtime" / "localflow.db")
    first = TaskService(root, store, SystemdExecutor(root), max_concurrency=1)
    task = first.submit(
        TaskCreate(
            name="finish-while-down",
            working_directory=str(root),
            command=["/bin/sh", "-c", "sleep .3; printf finished-offline"],
        )
    )
    await first.start()
    for _ in range(100):
        await asyncio.sleep(0.02)
        if control_socket_path(root, task.id).exists():
            break
    await first.stop()
    store.close()
    await asyncio.sleep(0.6)

    recovered_store = Store(root / "runtime" / "localflow.db")
    recovered = TaskService(root, recovered_store, SystemdExecutor(root), max_concurrency=1)
    await recovered.start()
    result = recovered_store.get_task(task.id)
    assert result.state == "succeeded"
    assert result.exit_code == 0
    assert b"finished-offline" in recovered.read_log(task.id)[0]
    await recovered.stop()
    recovered_store.close()
