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


def test_one_request_inline_configuration_uses_plugin_and_creates_batch(
    admin: TestClient, root: Path
) -> None:
    payload = {
        "configuration": {
            "plugin": "command",
            "name": "inline-api",
            "working_directory": str(root),
            "command": ["echo", "from-inline-config"],
            "labels": ["api"],
        },
        "inputs": {},
    }
    created = admin.post(
        "/api/v1/runs", json=payload, headers={"Idempotency-Key": "inline-run"}
    )
    assert created.status_code == 202
    assert created.json()["count"] == 1
    assert (
        admin.post(
            "/api/v1/runs", json=payload, headers={"Idempotency-Key": "inline-run"}
        ).json()
        == created.json()
    )
    task = admin.get(f"/api/v1/tasks/{created.json()['task_ids'][0]}").json()
    assert task["name"] == "inline-api"
    assert task["plugin_snapshot"]["name"] == "command"


def test_inline_configuration_rejects_missing_or_unknown_plugin(admin: TestClient) -> None:
    missing = admin.post("/api/v1/runs", json={"configuration": {}, "inputs": {}})
    assert missing.status_code == 422
    unknown = admin.post(
        "/api/v1/runs",
        json={"configuration": {"plugin": "does-not-exist"}, "inputs": {}},
    )
    assert unknown.status_code == 404

    invalid = admin.post(
        "/api/v1/runs",
        json={
            "configuration": {
                "plugin": "command",
                "name": "invalid",
                "working_directory": 42,
                "command": ["echo", "must-not-run"],
            },
            "inputs": {},
        },
    )
    assert invalid.status_code == 422
    assert "working_directory" in str(invalid.json()["detail"]["errors"])

    undeclared = admin.post(
        "/api/v1/runs",
        json={
            "configuration": {
                "plugin": "command",
                "name": "hidden-command",
                "working_directory": ".",
                "command": ["echo", "configured"],
            },
            "inputs": {"command": ["echo", "overridden"]},
        },
    )
    assert undeclared.status_code == 422
    assert "not declared" in undeclared.json()["detail"]
