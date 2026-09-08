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
