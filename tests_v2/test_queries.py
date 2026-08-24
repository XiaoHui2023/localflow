from datetime import UTC, datetime, timedelta
from pathlib import Path

from localflow.models import TaskCreate, TaskState
from localflow.storage import Store


def test_time_name_state_and_label_filters(root: Path) -> None:
    store = Store(root / "runtime" / "localflow.db")
    task = store.create_task(
        "task-a",
        TaskCreate(
            name="nightly smoke",
            working_directory=str(root),
            command=["true"],
            labels=["nightly", "smoke"],
        ),
    )
    start = datetime.now(UTC)
    store.transition(
        task.id,
        [TaskState.QUEUED],
        TaskState.RUNNING,
        started_at=start.isoformat(),
    )
    end = start + timedelta(seconds=5)
    store.transition(
        task.id,
        [TaskState.RUNNING],
        TaskState.SUCCEEDED,
        ended_at=end.isoformat(),
        exit_code=0,
    )
    assert [item.id for item in store.list_tasks(states=["succeeded"])] == [task.id]
    assert [item.id for item in store.list_tasks(labels=["nightly", "smoke"])] == [task.id]
    assert [item.id for item in store.list_tasks(name="smoke")] == [task.id]
    assert store.list_tasks(started_from=(start + timedelta(seconds=1)).isoformat()) == []
    assert store.list_tasks(ended_from=start.isoformat(), ended_to=end.isoformat())[0].id == task.id
    store.close()
