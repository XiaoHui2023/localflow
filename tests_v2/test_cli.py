from pathlib import Path
from types import ModuleType

import pytest

from localflow import cli


def test_source_entry_uses_current_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delattr(cli.sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    assert cli.application_root() == tmp_path.resolve()


def test_frozen_entry_uses_executable_directory(monkeypatch, tmp_path: Path) -> None:
    binary = tmp_path / "release" / "localflow"
    binary.parent.mkdir()
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli.sys, "executable", str(binary))
    monkeypatch.chdir(tmp_path)
    assert cli.application_root() == binary.parent.resolve()


def test_public_entry_starts_directly_without_arguments(monkeypatch, tmp_path: Path) -> None:
    called = []
    monkeypatch.setattr(cli.sys, "argv", ["localflow"])
    monkeypatch.setattr(cli, "application_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_run_internal_mode", lambda: False)
    monkeypatch.setattr(cli, "_serve", called.append)
    cli.main()
    assert called == [tmp_path]


@pytest.mark.parametrize(
    "arguments",
    [["--help"], ["init"], ["serve", "--root", "/tmp/localflow"]],
)
def test_public_entry_rejects_every_argument_before_starting(
    monkeypatch, arguments: list[str]
) -> None:
    monkeypatch.setattr(cli.sys, "argv", ["localflow", *arguments])
    monkeypatch.setattr(
        cli, "_serve", lambda _root: pytest.fail("server must not start with arguments")
    )
    with pytest.raises(SystemExit, match="does not accept arguments"):
        cli.main()


def test_frozen_supervisor_environment_is_not_inherited(monkeypatch, tmp_path: Path) -> None:
    task_id = "a" * 32
    supervisor = ModuleType("localflow.supervisor")
    supervisor.supervise = lambda root, task: 17 if (root, task) == (tmp_path, task_id) else 99
    monkeypatch.setitem(cli.sys.modules, "localflow.supervisor", supervisor)
    monkeypatch.setenv("LOCALFLOW_INTERNAL_MODE", "supervisor")
    monkeypatch.setenv("LOCALFLOW_INTERNAL_ROOT", str(tmp_path))
    monkeypatch.setenv("LOCALFLOW_INTERNAL_TASK", task_id)
    with pytest.raises(SystemExit) as stopped:
        cli._run_internal_mode()
    assert stopped.value.code == 17
    assert "LOCALFLOW_INTERNAL_MODE" not in cli.os.environ
    assert "LOCALFLOW_INTERNAL_ROOT" not in cli.os.environ
    assert "LOCALFLOW_INTERNAL_TASK" not in cli.os.environ
