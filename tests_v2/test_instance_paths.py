from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from localflow.api import create_app
from localflow.auth import AuthManager
from localflow.executor import SystemdExecutor
from localflow.models import TaskCreate
from localflow.paths import (
    STATE_FORMAT_VERSION,
    STATE_MARKER,
    InstanceLock,
    LocalFlowPaths,
    StateCompatibilityError,
    initialize_state_root,
    state_instance_id,
)
from localflow.settings import Settings, initialize_config_root


def test_default_paths_keep_dynamic_state_in_hidden_startup_directory(tmp_path: Path) -> None:
    paths = LocalFlowPaths.resolve(startup_directory=tmp_path)
    assert paths.config_root == tmp_path.resolve()
    assert paths.state_root == (tmp_path / ".localflow").resolve()


def test_two_instances_share_configuration_but_not_state_or_working_root(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "shared"
    state_a = tmp_path / "alpha"
    state_b = tmp_path / "beta"
    initialize_config_root(config_root)
    settings = Settings.model_validate({"execution": {"backend": "subprocess"}})
    app_a = create_app(config_root, state_root=state_a, settings=settings, start_scheduler=False)
    app_b = create_app(config_root, state_root=state_b, settings=settings, start_scheduler=False)
    try:
        task_a = app_a.state.tasks.submit(
            TaskCreate(name="alpha", working_directory="cases", command=["probe"])
        )
        task_b = app_b.state.tasks.submit(
            TaskCreate(name="beta", working_directory="cases", command=["probe"])
        )
        assert Path(task_a.working_directory) == (config_root / "cases").resolve()
        assert Path(task_b.working_directory) == (config_root / "cases").resolve()
        assert app_a.state.store.get_task(task_a.id).name == "alpha"
        with pytest.raises(KeyError):
            app_b.state.store.get_task(task_a.id)
        assert app_b.state.store.get_task(task_b.id).name == "beta"
        assert (state_a / "logs" / task_a.id / "output.log").is_file()
        assert not (state_b / "logs" / task_a.id).exists()
        assert (state_b / "logs" / task_b.id / "output.log").is_file()
        assert not (config_root / "runtime").exists()
        assert not (config_root / "logs").exists()
        assert (config_root / "secrets" / "api-key").is_file()
        assert app_a.state.auth.api_path == app_b.state.auth.api_path
        assert state_instance_id(state_a) != state_instance_id(state_b)
    finally:
        app_a.state.store.close()
        app_b.state.store.close()


def test_reopening_selected_state_recovers_only_its_history(tmp_path: Path) -> None:
    config_root = tmp_path / "shared"
    state_root = tmp_path / "instance"
    settings = Settings.model_validate({"execution": {"backend": "subprocess"}})
    first = create_app(config_root, state_root=state_root, settings=settings, start_scheduler=False)
    task = first.state.tasks.submit(
        TaskCreate(name="persistent", working_directory=".", command=["probe"])
    )
    first.state.store.close()
    first_instance_id = state_instance_id(state_root)
    restarted = create_app(
        config_root, state_root=state_root, settings=settings, start_scheduler=False
    )
    try:
        assert restarted.state.store.get_task(task.id).name == "persistent"
        assert state_instance_id(state_root) == first_instance_id
    finally:
        restarted.state.store.close()


def test_instance_lock_rejects_same_state_until_owner_releases(tmp_path: Path) -> None:
    with (
        InstanceLock(tmp_path),
        pytest.raises(RuntimeError, match="already in use"),
        InstanceLock(tmp_path),
    ):
        pass
    with InstanceLock(tmp_path):
        pass


def test_systemd_units_are_namespaced_by_state_directory(tmp_path: Path) -> None:
    alpha = SystemdExecutor(tmp_path / "alpha")._unit_name("same-task")
    beta = SystemdExecutor(tmp_path / "beta")._unit_name("same-task")
    assert alpha != beta
    assert alpha.endswith("-task-same-task.service")


def test_concurrent_shared_secret_initialization_creates_one_stable_pair(
    tmp_path: Path,
) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        managers = list(pool.map(lambda _index: AuthManager(tmp_path), range(32)))
    admin_values = {manager.admin_path.read_text(encoding="ascii") for manager in managers}
    api_values = {manager.api_path.read_text(encoding="ascii") for manager in managers}
    assert len(admin_values) == len(api_values) == 1
    assert next(iter(admin_values)).strip()
    assert next(iter(api_values)).strip()
    assert not list((tmp_path / "secrets").glob(".*.new"))


def test_concurrent_shared_configuration_bootstrap_is_idempotent(tmp_path: Path) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _index: initialize_config_root(tmp_path), range(16)))
    assert (tmp_path / "config.yaml").is_file()
    assert (tmp_path / "plugins" / "command.py").is_file()
    assert (tmp_path / "plugins" / "verification.py").is_file()
    assert not list((tmp_path / "plugins").glob(".*.localflow-update"))


def test_invalid_state_marker_quarantines_only_dynamic_state(tmp_path: Path) -> None:
    config = tmp_path / "shared-config"
    config.mkdir()
    (config / "keep.yaml").write_text("keep: true\n", encoding="utf-8")
    state = tmp_path / "state"
    (state / "runtime").mkdir(parents=True)
    (state / "runtime" / "broken.db").write_text("broken", encoding="utf-8")
    (state / STATE_MARKER).write_text("not json", encoding="utf-8")
    initialize_state_root(state)
    assert (config / "keep.yaml").read_text(encoding="utf-8") == "keep: true\n"
    assert not (state / "runtime" / "broken.db").exists()
    assert list((state / "recovery").glob("*-invalid-marker/runtime/broken.db"))
    marker = json.loads((state / STATE_MARKER).read_text(encoding="utf-8"))
    assert marker["format"] == STATE_FORMAT_VERSION
    assert marker["instance_id"]


def test_newer_state_format_fails_closed_without_mutation(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    marker = state / STATE_MARKER
    marker.write_text(json.dumps({"format": STATE_FORMAT_VERSION + 1}), encoding="utf-8")
    payload = state / "runtime" / "keep.db"
    payload.parent.mkdir()
    payload.write_text("future", encoding="utf-8")
    with pytest.raises(StateCompatibilityError, match="newer than supported"):
        initialize_state_root(state)
    assert payload.read_text(encoding="utf-8") == "future"
