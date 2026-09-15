from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

import pytest

from localflow.executor import SubprocessExecutor
from localflow.models import TaskCreate
from localflow.service import TaskService
from localflow.storage import Store


@pytest.mark.skipif(sys.platform != "linux", reason="Ubuntu shell contract")
@pytest.mark.asyncio
async def test_bashrc_alias_runs_in_frozen_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    root = tmp_path / "localflow"
    project = tmp_path / "external-project"
    home.mkdir()
    root.mkdir()
    project.mkdir()
    (home / ".bashrc").write_text(
        "alias localflow_profile_command='mkdir -p generated && pwd > generated/cwd.txt'\n"
        f"cd {root}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SHELL", "/bin/bash")
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="bashrc-alias",
            working_directory=str(project),
            command="localflow_profile_command",
        )
    )
    await service.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0.02)
            if store.get_task(task.id).ended_at:
                break
        assert store.get_task(task.id).state == "succeeded"
        assert (project / "generated" / "cwd.txt").read_text(
            encoding="utf-8"
        ).strip() == str(project)
        assert not (root / "generated").exists()
    finally:
        await service.stop()
        store.close()


@pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("tcsh") is None,
    reason="tcsh is not installed",
)
@pytest.mark.asyncio
async def test_detected_tcsh_loads_cshrc_and_preserves_frozen_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    root = tmp_path / "localflow"
    project = tmp_path / "external-project"
    home.mkdir()
    root.mkdir()
    project.mkdir()
    (home / ".cshrc").write_text(
        "alias localflow_csh_command 'mkdir -p generated; pwd > generated/cwd.txt'\n"
        f"cd {root}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SHELL", "/bin/tcsh")
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="cshrc-alias",
            working_directory=str(project),
            command="localflow_csh_command",
        )
    )
    await service.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0.02)
            if store.get_task(task.id).ended_at:
                break
        assert store.get_task(task.id).state == "succeeded"
        assert (project / "generated" / "cwd.txt").read_text(
            encoding="utf-8"
        ).strip() == str(project)
        assert not (root / "generated").exists()
    finally:
        await service.stop()
        store.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Ubuntu shell contract")
@pytest.mark.asyncio
async def test_bash_source_environment_is_private_to_one_task(tmp_path: Path) -> None:
    root = tmp_path / "localflow"
    project = tmp_path / "project"
    root.mkdir()
    project.mkdir()
    (project / "task-env.sh").write_text(
        "export LOCALFLOW_SCOPED_VALUE=only-this-task\n"
        f"cd {root}\n",
        encoding="utf-8",
    )
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=None)
    sourced = service.submit(
        TaskCreate(
            name="sourced",
            working_directory=str(project),
            shell="/bin/bash",
            source="task-env.sh",
            command="printf '%s' \"$LOCALFLOW_SCOPED_VALUE\" > sourced.txt",
        )
    )
    independent = service.submit(
        TaskCreate(
            name="independent",
            working_directory=str(project),
            shell="/bin/bash",
            command="printf '%s' \"${LOCALFLOW_SCOPED_VALUE-unset}\" > independent.txt",
        )
    )
    await service.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0.02)
            if all(store.get_task(task.id).ended_at for task in (sourced, independent)):
                break
        assert store.get_task(sourced.id).state == "succeeded"
        assert store.get_task(independent.id).state == "succeeded"
        assert (project / "sourced.txt").read_text() == "only-this-task"
        assert (project / "independent.txt").read_text() == "unset"
        output = (root / "logs" / sourced.id / "output.log").read_text()
        assert "] process.source " in output
        assert f"path={str(project / 'task-env.sh')!r}" in output
    finally:
        await service.stop()
        store.close()


@pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("tcsh") is None,
    reason="tcsh is not installed",
)
@pytest.mark.asyncio
async def test_tcsh_sources_csh_file_before_user_command(tmp_path: Path) -> None:
    root = tmp_path / "localflow"
    project = tmp_path / "project"
    root.mkdir()
    project.mkdir()
    (project / "task-env.csh").write_text(
        "setenv LOCALFLOW_SCOPED_VALUE csh-task\n"
        f"cd {root}\n",
        encoding="utf-8",
    )
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="csh-source",
            working_directory=str(project),
            shell="/bin/tcsh",
            source="task-env.csh",
            command="printf '%s' \"$LOCALFLOW_SCOPED_VALUE\" > sourced.txt",
        )
    )
    await service.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0.02)
            if store.get_task(task.id).ended_at:
                break
        assert store.get_task(task.id).state == "succeeded"
        assert (project / "sourced.txt").read_text() == "csh-task"
    finally:
        await service.stop()
        store.close()
