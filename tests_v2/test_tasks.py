import shlex
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
    assert created.headers["location"] == f"/api/v1/tasks/{created.json()['task_id']}"
    assert created.headers["retry-after"] == "1"
    assert created.json()["task"]["href"] == created.headers["location"]
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


def test_direct_task_freezes_relative_working_directory_against_runtime_root(
    admin: TestClient, root: Path
) -> None:
    task_id = admin.post(
        "/api/v1/tasks",
        json={
            "name": "relative-cwd",
            "working_directory": "external-project",
            "command": ["true"],
        },
    ).json()["task_id"]
    task = admin.get(f"/api/v1/tasks/{task_id}").json()
    assert task["working_directory"] == str((root / "external-project").resolve())


def test_task_detail_hides_executor_wrapper_from_display_command(
    admin: TestClient, root: Path
) -> None:
    task_id = admin.post(
        "/api/v1/tasks",
        json={
            "name": "operator-command",
            "working_directory": str(root),
            "command": "make all CASE=smoke SEED=7",
        },
    ).json()["task_id"]
    task = admin.get(f"/api/v1/tasks/{task_id}").json()
    assert task["display_command"] == "make all CASE=smoke SEED=7"
    assert task["command"][1] == "-ic"


def test_task_detail_exposes_frozen_source_files(admin: TestClient, root: Path) -> None:
    environment = root / "toolchain setup.sh"
    environment.parent.mkdir(parents=True, exist_ok=True)
    environment.write_text("export MODE=fast\n", encoding="utf-8")
    task_id = admin.post(
        "/api/v1/tasks",
        json={
            "name": "sourced-task",
            "working_directory": str(root),
            "source": [environment.name],
            "command": "printf '%s' \"$MODE\"",
        },
    ).json()["task_id"]
    task = admin.get(f"/api/v1/tasks/{task_id}").json()
    assert task["source_files"] == [str(environment.resolve())]
    assert task["source_invocations"] == [
        f"source {shlex.quote(str(environment.resolve()))}"
    ]
    assert task["custom"]["_source_files"] == [str(environment.resolve())]


def test_task_detail_preserves_complete_source_statement(
    admin: TestClient, root: Path
) -> None:
    statement = "source scripts/setup.csh -env_path './toolchain profile.env'"
    task_id = admin.post(
        "/api/v1/tasks",
        json={
            "name": "source-statement",
            "working_directory": str(root),
            "source": statement,
            "command": "printf ready",
        },
    ).json()["task_id"]

    task = admin.get(f"/api/v1/tasks/{task_id}").json()

    assert task["source_files"] == []
    assert task["source_invocations"] == [statement]
    assert task["custom"]["_source_invocations"] == [{"statement": statement}]


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
    planned = admin.post("/api/v1/runs/plan", json=payload)
    assert planned.status_code == 200
    assert planned.json()["count"] == 1
    assert planned.json()["items"][0]["name"] == "inline-api"
    created = admin.post(
        "/api/v1/runs", json=payload, headers={"Idempotency-Key": "inline-run"}
    )
    assert created.status_code == 202
    assert created.json()["count"] == 1
    assert created.headers["location"] == f"/api/v1/batches/{created.json()['batch_id']}"
    assert created.headers["retry-after"] == "1"
    assert created.json()["batch"]["href"] == created.headers["location"]
    assert created.json()["tasks"] == [
        {
            "id": created.json()["task_ids"][0],
            "href": f"/api/v1/tasks/{created.json()['task_ids'][0]}",
        }
    ]
    assert (
        admin.post(
            "/api/v1/runs", json=payload, headers={"Idempotency-Key": "inline-run"}
        ).json()
        == created.json()
    )
    task = admin.get(f"/api/v1/tasks/{created.json()['task_ids'][0]}").json()
    assert task["name"] == "inline-api"
    assert task["plugin_snapshot"]["name"] == "command"


def test_configuration_plan_and_task_share_absolute_relative_cwd_snapshot(
    admin: TestClient, root: Path
) -> None:
    payload = {
        "configuration": {
            "plugin": "command",
            "name": "relative-config-cwd",
            "working_directory": "external-project",
            "command": ["true"],
        },
        "inputs": {},
    }
    expected = str((root / "external-project").resolve())
    plan = admin.post("/api/v1/runs/plan", json=payload)
    assert plan.status_code == 200
    assert plan.json()["items"][0]["working_directory"] == expected
    created = admin.post("/api/v1/runs", json=payload)
    task = admin.get(f"/api/v1/tasks/{created.json()['task_ids'][0]}").json()
    assert task["working_directory"] == expected


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


def test_plugin_contract_plan_and_saved_config_run_are_machine_complete(
    admin: TestClient,
) -> None:
    contract = admin.get("/api/v1/plugins/verification")
    assert contract.status_code == 200
    assert contract.json()["api"]["input_schema"]["additionalProperties"] is False
    assert {"cases", "case_runs", "runs", "seed"}.issubset(
        contract.json()["api"]["input_schema"]["properties"]
    )

    before = {item["id"] for item in admin.get("/api/v1/tasks").json()["items"]}
    inputs = {
        "inputs": {
            "cases": ["case-a"],
            "case_runs": {"case-a": 2},
            "seed": None,
        }
    }
    plan = admin.post("/api/v1/config/files/verification/demo.yaml/plan", json=inputs)
    assert plan.status_code == 200
    assert plan.json()["count"] == 2
    assert plan.json()["immutable_after_submit"] is True
    assert all("seed" in item["deferred_values"] for item in plan.json()["items"])
    after = {item["id"] for item in admin.get("/api/v1/tasks").json()["items"]}
    assert after == before

    first = admin.post(
        "/api/v1/config/files/verification/demo.yaml/runs",
        json=inputs,
        headers={"Idempotency-Key": "saved-verification"},
    )
    second = admin.post(
        "/api/v1/config/files/verification/demo.yaml/runs",
        json=inputs,
        headers={"Idempotency-Key": "saved-verification"},
    )
    assert first.status_code == 202
    assert second.json() == first.json()
    assert first.json()["count"] == 2
    records = [
        admin.get(f"/api/v1/tasks/{task_id}").json()
        for task_id in first.json()["task_ids"]
    ]
    seeds = [record["custom"]["seed"] for record in records]
    assert seeds[1] == seeds[0] + 1
    assert all("${seed}" not in record["command"] for record in records)


def test_recent_configurations_follow_accepted_runs_and_workspace_moves(
    admin: TestClient,
) -> None:
    assert admin.get("/api/v1/config/recent").json() == {"items": []}

    command = admin.post(
        "/api/v1/config/files/command/hello-world.yaml/runs",
        json={"inputs": {}},
    )
    assert command.status_code == 202
    verification = admin.post(
        "/api/v1/config/files/verification/demo.yaml/runs",
        json={"inputs": {"cases": ["case-a"], "case_runs": {"case-a": 1}}},
    )
    assert verification.status_code == 202

    recent = admin.get("/api/v1/config/recent").json()["items"]
    assert [item["path"] for item in recent] == [
        "config/verification/demo.yaml",
        "config/command/hello-world.yaml",
    ]
    assert recent[0]["name"] == "demo.yaml"
    assert isinstance(recent[0]["labels"], list)
    assert recent[0]["last_used_at"] >= recent[1]["last_used_at"]

    moved = admin.post(
        "/api/v1/workspace/moves",
        json={
            "source": "config/command/hello-world.yaml",
            "target": "config/command/renamed.yaml",
        },
    )
    assert moved.status_code == 200
    paths = [item["path"] for item in admin.get("/api/v1/config/recent").json()["items"]]
    assert "config/command/renamed.yaml" in paths
    assert "config/command/hello-world.yaml" not in paths
