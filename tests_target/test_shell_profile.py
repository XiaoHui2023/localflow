from __future__ import annotations

import asyncio
import shlex
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
    (project / "task env.sh").write_text(
        "export LOCALFLOW_SCOPED_VALUE=only-this-task\n"
        f"cd {root}\n",
        encoding="utf-8",
    )
    (project / "task-env-second.sh").write_text(
        "export LOCALFLOW_SCOPED_VALUE=\"${LOCALFLOW_SCOPED_VALUE}-second\"\n",
        encoding="utf-8",
    )
    (project / "task-env-link.sh").symlink_to("task-env-second.sh")
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=None)
    sourced = service.submit(
        TaskCreate(
            name="sourced",
            working_directory=str(project),
            shell="/bin/bash",
            source=["task env.sh", "task-env-link.sh"],
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
        assert (project / "sourced.txt").read_text() == "only-this-task-second"
        assert (project / "independent.txt").read_text() == "unset"
        output = (root / "logs" / sourced.id / "output.log").read_text()
        assert "] process.source " in output
        assert f"path={str((project / 'task env.sh').resolve())!r}" in output
        assert f"path={str((project / 'task-env-link.sh').resolve())!r}" in output
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
            source=["task-env.csh"],
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


@pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("tcsh") is None,
    reason="tcsh is not installed",
)
@pytest.mark.asyncio
async def test_tcsh_source_keeps_interactive_contract_for_vendor_setup_files(
    tmp_path: Path,
) -> None:
    """Reproduce a csh setup file that rejects the non-interactive ``-c`` path.

    Vendors commonly permit a setup file from an interactive csh session, but
    require an ``-env_path`` escape hatch when the same file sees itself being
    loaded by an unattended script.  LocalFlow's source list has no vendor
    arguments by design, so its selected csh must retain the interactive shell
    contract instead of forcing every such user to invent a wrapper.
    """
    root = tmp_path / "localflow"
    project = tmp_path / "project"
    root.mkdir()
    project.mkdir()
    (project / "vendor-setup.csh").write_text(
        "if ( ! $?prompt ) then\n"
        "  echo 'Error: Environment variables file does not exist. If called inside a script make sure you are using -env_path <path to env file>'\n"
        "  exit 64\n"
        "endif\n"
        "setenv LOCALFLOW_VENDOR_READY yes\n",
        encoding="utf-8",
    )
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=1)
    task = service.submit(
        TaskCreate(
            name="interactive-csh-source",
            working_directory=str(project),
            shell="/bin/tcsh",
            source=["vendor-setup.csh"],
            command="printf '%s' \"$LOCALFLOW_VENDOR_READY\" > sourced.txt",
        )
    )
    await service.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0.02)
            if store.get_task(task.id).ended_at:
                break
        assert store.get_task(task.id).state == "succeeded"
        assert (project / "sourced.txt").read_text() == "yes"
    finally:
        await service.stop()
        store.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Ubuntu shell contract")
@pytest.mark.asyncio
async def test_source_wrapper_can_initialize_a_vendor_environment(tmp_path: Path) -> None:
    root = tmp_path / "localflow"
    project = tmp_path / "project"
    root.mkdir()
    project.mkdir()
    environment = project / "toolchain profile.env"
    environment.write_text("argument-value\n", encoding="utf-8")
    (project / "task-env.sh").write_text(
        "test \"$1\" = -env_path || exit 41\n"
        "test -f \"$2\" || exit 42\n"
        "export LOCALFLOW_SCOPED_VALUE=\"$(cat \"$2\")\"\n",
        encoding="utf-8",
    )
    (project / "localflow-environment.sh").write_text(
        "source task-env.sh -env_path " + shlex.quote(str(environment)) + "\n",
        encoding="utf-8",
    )
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=None)
    task = service.submit(
        TaskCreate(
            name="source-wrapper",
            working_directory=str(project),
            shell="/bin/bash",
            source=["localflow-environment.sh"],
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
        assert (project / "sourced.txt").read_text() == "argument-value"
        output = (root / "logs" / task.id / "output.log").read_text()
        assert "] process.source " in output
        assert "localflow-environment.sh" in output
    finally:
        await service.stop()
        store.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Ubuntu shell contract")
@pytest.mark.asyncio
async def test_source_path_list_adapts_to_posix_sh_and_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "localflow"
    project = tmp_path / "project"
    root.mkdir()
    project.mkdir()
    (project / "environment.sh").write_text(
        "export LOCALFLOW_SOURCE_VALUE=from-sh\n", encoding="utf-8"
    )
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, SubprocessExecutor(), max_concurrency=None)
    valid = service.submit(
        TaskCreate(
            name="source-posix-sh",
            working_directory=str(project),
            shell="/bin/sh",
            source=["./environment.sh"],
            command="printf '%s' \"$LOCALFLOW_SOURCE_VALUE\" > sourced-sh.txt",
        )
    )
    invalid = service.submit(
        TaskCreate(
            name="source-failure",
            working_directory=str(project),
            shell="/bin/sh",
            source=["./missing-environment.sh"],
            command="touch must-not-exist",
        )
    )
    await service.start()
    try:
        for _ in range(200):
            await asyncio.sleep(0.02)
            if all(store.get_task(task.id).ended_at for task in (valid, invalid)):
                break
        assert store.get_task(valid.id).state == "succeeded"
        assert (project / "sourced-sh.txt").read_text() == "from-sh"
        assert store.get_task(invalid.id).state == "failed"
        assert not (project / "must-not-exist").exists()
    finally:
        await service.stop()
        store.close()
