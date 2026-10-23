from __future__ import annotations

import pytest

from localflow.executor import SystemdExecutor
from localflow.models import TaskCreate
from localflow.storage import Store


class _SystemctlResult:
    def __init__(self, state: bytes) -> None:
        self.returncode = 0
        self._state = state

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._state, b""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "owns_process_tree"),
    [
        (b"LoadState=loaded\nActiveState=active\n", True),
        (b"LoadState=loaded\nActiveState=deactivating\n", True),
        (b"LoadState=loaded\nActiveState=inactive\n", False),
        (b"LoadState=loaded\nActiveState=failed\n", False),
        (b"LoadState=not-found\nActiveState=inactive\n", False),
    ],
)
async def test_systemd_process_ownership_requires_an_explicit_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    state: bytes,
    owns_process_tree: bool,
) -> None:
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return _SystemctlResult(state)

    monkeypatch.setattr(
        "localflow.executor.asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )
    executor = SystemdExecutor(tmp_path)
    assert (
        await executor._unit_owns_process_tree("localflow-task-test.service") is owns_process_tree
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [229, 237, 239, 240, 245, 249, 252, 255, 0])
async def test_systemd_launch_options_match_client_capabilities(monkeypatch, tmp_path, version):
    commands = []

    async def spawn(*args, **_kwargs):
        commands.append(args)
        return _SystemctlResult(f"systemd {version}\n".encode() if args[-1] == "--version" else b"")

    monkeypatch.setattr("localflow.executor.asyncio.create_subprocess_exec", spawn)
    store = Store(tmp_path / "runtime/localflow.db")
    task = store.create_task("probe", TaskCreate(
        name="probe", working_directory=str(tmp_path), command=["true"],
    ))
    executor = SystemdExecutor(tmp_path)
    await executor.start(task, tmp_path / "output.log")
    await executor.start(task, tmp_path / "output.log")
    assert sum(command[-1] == "--version" for command in commands) == 1
    for command in commands[1:]:
        assert ("--collect" in command) == (version >= 236)
        assert ("Type=exec" in command) == (version >= 240)
        assert ("Type=simple" in command) == (version < 240)
    store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage,target,signal", [
    ("sigint", "main", "SIGINT"), ("sigterm", "main", "SIGTERM"),
    ("sigkill", "all", "SIGKILL"),
])
async def test_systemd_stop_uses_old_and_new_compatible_selector(
    monkeypatch, tmp_path, stage, target, signal,
):
    commands = []

    async def spawn(*args, **_kwargs):
        commands.append(args)
        return _SystemctlResult(b"")

    monkeypatch.setattr("localflow.executor.asyncio.create_subprocess_exec", spawn)
    assert await SystemdExecutor(tmp_path).interrupt("probe", stage)
    assert len(commands) == 1
    assert f"--kill-who={target}" in commands[0]
    assert f"--signal={signal}" in commands[0]
    assert not any(arg.startswith("--kill-whom") for arg in commands[0])


@pytest.mark.asyncio
async def test_systemd_stop_failure_is_not_reported_as_a_success(monkeypatch, tmp_path):
    class Denied(_SystemctlResult):
        returncode = 1

        def __init__(self):
            self.returncode = 1

        async def communicate(self):
            return b"", b"Access denied"

    async def spawn(*args, **_kwargs):
        return Denied() if "kill" in args else _SystemctlResult(b"LoadState=loaded\nActiveState=active\n")

    monkeypatch.setattr("localflow.executor.asyncio.create_subprocess_exec", spawn)
    with pytest.raises(RuntimeError, match="Access denied"):
        await SystemdExecutor(tmp_path).interrupt("probe", "sigkill")
