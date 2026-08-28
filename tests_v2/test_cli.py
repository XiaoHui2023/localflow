from contextlib import nullcontext
from pathlib import Path
from types import ModuleType

import pytest

from localflow import cli
from localflow import executor as executor_module
from localflow.executor import SystemdExecutor
from localflow.models import TaskCreate
from localflow.settings import initialize_root, load_settings
from localflow.storage import Store


def test_controller_disables_current_and_legacy_uvicorn_signal_capture() -> None:
    class Server:
        def install_signal_handlers(self) -> None:
            raise AssertionError("legacy Uvicorn signal capture remained active")

        def capture_signals(self):
            raise AssertionError("current Uvicorn signal capture remained active")

    server = Server()
    cli._disable_uvicorn_signal_capture(server)
    server.install_signal_handlers()
    assert server.capture_signals is nullcontext
    with server.capture_signals():
        pass


def test_source_entry_uses_current_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delattr(cli.sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    assert cli.application_root() == tmp_path.resolve()


def test_new_root_defaults_to_lan_listener(tmp_path: Path) -> None:
    initialize_root(tmp_path)
    config = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "bind:" not in config
    assert load_settings(tmp_path).server.bind == "0.0.0.0"
    assert load_settings(tmp_path).execution.backend == "auto"


def test_frozen_entry_uses_executable_directory(monkeypatch, tmp_path: Path) -> None:
    binary = tmp_path / "release" / "localflow"
    binary.parent.mkdir()
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli.sys, "executable", str(binary))
    monkeypatch.chdir(tmp_path)
    assert cli.application_root() == binary.parent.resolve()


def test_staticx_entry_uses_outer_executable_directory(monkeypatch, tmp_path: Path) -> None:
    outer = tmp_path / "release" / "localflow"
    inner = tmp_path / "staticx-temporary" / "localflow"
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli.sys, "executable", str(inner))
    monkeypatch.setenv("STATICX_PROG_PATH", str(outer))
    monkeypatch.chdir(tmp_path)
    assert cli.application_root() == outer.parent.resolve()


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


@pytest.mark.asyncio
async def test_staticx_systemd_supervisor_reenters_outer_executable(
    monkeypatch, tmp_path: Path
) -> None:
    initialize_root(tmp_path)
    task = Store(tmp_path / "runtime" / "localflow.db").create_task(
        "b" * 32,
        TaskCreate(name="probe", working_directory=str(tmp_path), command=["true"]),
    )
    outer = tmp_path / "localflow"
    inner = tmp_path / "staticx-temporary" / "localflow"
    captured = []

    class Completed:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def create_subprocess(*command, **_kwargs):
        captured.extend(command)
        return Completed()

    monkeypatch.setattr(executor_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(executor_module.sys, "executable", str(inner))
    monkeypatch.setenv("STATICX_PROG_PATH", str(outer))
    monkeypatch.setattr(executor_module.asyncio, "create_subprocess_exec", create_subprocess)
    await SystemdExecutor(tmp_path).start(task, tmp_path / "logs" / "output.log")
    assert captured[-1] == str(outer)
    assert str(inner) not in captured
