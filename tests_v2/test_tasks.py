from pathlib import Path

from fastapi.testclient import TestClient


def test_anonymous_is_summary_and_cannot_submit(
    client: TestClient, admin: TestClient, root: Path
) -> None:
    payload = {
        "name": "hello",
        "working_directory": str(root),
        "command": ["echo", "secret"],
        "labels": ["smoke", "linux"],
        "custom": {"secret": "hidden"},
    }
    created = admin.post("/api/v1/tasks", json=payload, headers={"Idempotency-Key": "same"})
    assert created.status_code == 202
    assert (
        admin.post("/api/v1/tasks", json=payload, headers={"Idempotency-Key": "same"}).json()
        == created.json()
    )
    admin.cookies.clear()
    listing = client.get("/api/v1/tasks").json()["items"]
    assert listing[0]["name"] == "hello"
    assert (
        "command" not in listing[0]
        and "working_directory" not in listing[0]
        and "custom" not in listing[0]
    )
    assert client.post("/api/v1/tasks", json=payload).status_code == 403
    assert client.post(f"/api/v1/tasks/{created.json()['task_id']}/interrupt").status_code == 403


def test_task_snapshot_is_immutable(admin: TestClient, root: Path) -> None:
    payload = {
        "name": "snapshot",
        "working_directory": str(root),
        "command": ["echo", "one"],
        "labels": ["a"],
    }
    task_id = admin.post("/api/v1/tasks", json=payload).json()["task_id"]
    payload["command"][1] = "two"
    assert admin.get(f"/api/v1/tasks/{task_id}").json()["command"] == ["echo", "one"]
