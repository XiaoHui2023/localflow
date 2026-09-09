from __future__ import annotations

import pytest

from localflow.executor import SystemdExecutor


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
