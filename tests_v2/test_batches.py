from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from localflow.models import DeferredValue, TaskCreate, TaskDraft
from localflow.service import TaskService
from localflow.storage import Store


class NoopExecutor:
    pass


def test_batch_and_tasks_are_written_in_one_transaction(root: Path) -> None:
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, NoopExecutor(), max_concurrency=1)  # type: ignore[arg-type]
    drafts = [
        TaskCreate(
            name=f"case-a #{index}",
            working_directory=str(root),
            command=["true"],
            labels=["case-a"],
        )
        for index in (1, 2)
    ]
    batch_id, records = service.submit_batch("verification", {"case": "a"}, drafts)
    batch = store.get_batch(batch_id)
    assert batch["task_ids"] == [record.id for record in records]
    assert batch["values"] == {"case": "a"}
    assert [item.name for item in records] == ["case-a #1", "case-a #2"]
    store.close()


def test_deferred_values_and_batch_are_one_transaction(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("localflow.storage.time.time", lambda: 1_700_000_000)
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, NoopExecutor(), max_concurrency=1)  # type: ignore[arg-type]
    automatic = DeferredValue(source="monotonic_unix", namespace="test.seed")
    good = TaskDraft(
        name="good",
        working_directory=str(root),
        command=["echo", "${seed}"],
        deferred_values={"seed": automatic},
    )
    collision = TaskDraft(
        name="collision",
        working_directory=str(root),
        command=["echo", "${seed}"],
        custom={"seed": 7},
        deferred_values={"seed": automatic},
    )
    with pytest.raises(ValueError, match="collide"):
        service.submit_batch("demo", {}, [good, collision])
    assert store.list_tasks() == []
    record = service.submit(good)
    assert record.custom["seed"] == 1_700_000_000
    store.close()


def test_concurrent_idempotent_batch_submission_creates_one_batch(root: Path) -> None:
    store = Store(root / "runtime" / "localflow.db")
    service = TaskService(root, store, NoopExecutor(), max_concurrency=1)  # type: ignore[arg-type]
    drafts = [TaskCreate(name="one", working_directory=str(root), command=["true"])]

    def submit():
        return service.submit_batch(
            "demo", {}, drafts, ("agent", "/api/v1/runs", "same-key")
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _value: submit(), range(2)))
    assert first[0] == second[0]
    assert [record.id for record in first[1]] == [record.id for record in second[1]]
    assert len(store.list_tasks()) == 1
    store.close()


def test_legacy_queued_runtime_seed_is_migrated_before_scheduling(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(root / "runtime" / "localflow.db")
    legacy = store.create_task(
        "legacy",
        TaskCreate(
            name="legacy",
            working_directory=str(root),
            command=["echo", "${seed}"],
            custom={"_runtime_seed": "unix"},
        ),
    )
    assert legacy.command[-1] == "${seed}"
    store.close()
    monkeypatch.setattr("localflow.storage.time.time", lambda: 1_700_000_000)
    store = Store(root / "runtime" / "localflow.db")
    migrated = store.get_task("legacy")
    assert migrated.command[-1] == "1700000000"
    assert migrated.custom == {"seed": 1_700_000_000}
    store.close()
