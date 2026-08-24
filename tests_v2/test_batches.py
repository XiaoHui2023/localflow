from pathlib import Path

from localflow.models import TaskCreate
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
