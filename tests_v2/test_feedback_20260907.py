from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from localflow.api import create_app
from localflow.settings import ExecutionSettings, ServerSettings, Settings


def test_resource_explorer_projects_only_config_children(admin: TestClient) -> None:
    payload = admin.get("/api/v1/workspace").json()
    paths = {item["path"] for item in payload["items"]}

    assert "config" not in paths
    assert not any(path == "plugins" or path.startswith("plugins/") for path in paths)
    assert any(path.startswith("config/") for path in paths)


def test_workspace_save_is_not_blocked_by_plugin_diagnostics(
    admin: TestClient, root: Path
) -> None:
    target = "config/free-edit.yaml"
    content = "plugin: command\nlabels: freely editable extra input\nextra_inputs: true\n"

    response = admin.put(
        f"/api/v1/workspace/files/{target}",
        headers={"If-Match": "*"},
        json={"content": content},
    )

    assert response.status_code == 200, response.text
    assert (root / target).read_text(encoding="utf-8") == content
    opened = admin.get(f"/api/v1/workspace/files/{target}").json()
    assert opened["diagnosis"]["valid"] is True
    assert opened["run_diagnosis"]["runnable"] is False
    assert opened["run_diagnosis"]["errors"]

    broken = "plugin: ["
    saved = admin.put(
        f"/api/v1/workspace/files/{target}",
        headers={"If-Match": opened["version"]},
        json={"content": broken},
    )
    assert saved.status_code == 200, saved.text
    diagnosis = admin.post(
        "/api/v1/config/files/free-edit.yaml/diagnosis",
        json={"content": broken},
    ).json()["diagnosis"]
    assert diagnosis["valid"] is False
    assert diagnosis["errors"]
    assert diagnosis["issues"] == [
        {
            "message": diagnosis["errors"][0],
            "severity": "error",
            "line": 1,
            "column": 10,
            "end_line": 1,
            "end_column": 11,
        }
    ]


def test_live_diagnosis_returns_resolved_document_and_run_errors(admin) -> None:
    response = admin.post(
        "/api/v1/config/files/debug.yaml/diagnosis",
        json={
            "content": "plugin: command\nlabels: wrong\nvisible: ${answer}\nvariables:\n  answer: 42\n"
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["diagnosis"]["valid"] is True
    assert result["document"]["visible"] == "${answer}"
    assert result["resolved_document"]["visible"] == 42
    assert result["plugin"] == "command"
    assert result["run_diagnosis"]["runnable"] is False
    assert any("labels" in item for item in result["run_diagnosis"]["errors"])
    assert any("working_directory" in item for item in result["run_diagnosis"]["errors"])
    assert any("command" in item for item in result["run_diagnosis"]["errors"])


def test_verification_inspection_shows_resolved_logs_without_requiring_files(
    admin: TestClient, root: Path
) -> None:
    project = root / "simulation"
    project.mkdir()
    (root / "cases" / "case-a").mkdir(parents=True, exist_ok=True)
    config = root / "config" / "verification" / "inspect-logs.yaml"
    config.write_text(
        "plugin: verification\n"
        f"working_directory: {project.as_posix()}\n"
        "case_directory: cases\n"
        "command: make run\n"
        "labels: [smoke]\n"
        "compile_logs: ['logs/${case}.compile.log', 'logs/${case}.lint.log']\n"
        "run_logs: ['logs/${case}.run.log', 'logs/${case}.trace.log']\n",
        encoding="utf-8",
    )

    response = admin.post(
        "/api/v1/config/files/verification/inspect-logs.yaml/inspection",
        json={"inputs": {"cases": ["case-a"], "case_runs": {"case-a": 1}}},
    )

    assert response.status_code == 200, response.text
    items = {item["name"]: item for item in response.json()["items"]}
    assert items["compile_logs"]["severity"] == "info"
    assert items["run_logs"]["severity"] == "info"
    assert items["labels"]["kind"] == "tokens"
    assert items["labels"]["value"] == ["smoke"]
    assert items["compile_logs"]["kind"] == "code-list"
    assert items["run_logs"]["kind"] == "code-list"
    assert items["compile_logs"]["value"] == [
        str(project / "logs" / "${case}.compile.log"),
        str(project / "logs" / "${case}.lint.log"),
    ]
    assert items["run_logs"]["value"] == [
        str(project / "logs" / "${case}.run.log"),
        str(project / "logs" / "${case}.trace.log"),
    ]


def test_configured_working_directory_owns_relative_side_effects(
    root: Path,
) -> None:
    project = root.parent / "external project"
    project.mkdir()
    (project / "required.txt").write_text("external", encoding="utf-8")
    (root / "cases" / "case-a").mkdir(parents=True, exist_ok=True)
    configuration = {
        "plugin": "verification",
        "working_directory": str(project),
        "case_directory": "cases",
        "command": [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "assert Path('required.txt').read_text() == 'external'; "
                "Path('generated').mkdir(); "
                "Path('generated/result.txt').write_text(str(Path.cwd()))"
            ),
        ],
    }
    settings = Settings(
        server=ServerSettings(anonymous_access="summary"),
        execution=ExecutionSettings(backend="subprocess", max_concurrency=1),
    )
    app = create_app(root, settings=settings, start_scheduler=True)
    with TestClient(app, base_url="http://127.0.0.1") as admin:
        key = (root / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
        session = admin.post("/api/v1/auth/local-sessions", json={"key": key}).json()
        admin.headers.update({"Origin": "http://127.0.0.1", "X-CSRF-Token": session["csrf_token"]})
        response = admin.post(
            "/api/v1/runs",
            json={
                "configuration": configuration,
                "inputs": {"cases": ["case-a"], "case_runs": {"case-a": 1}},
            },
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["task_ids"][0]
        deadline = time.monotonic() + 10
        task = None
        while time.monotonic() < deadline:
            task = admin.get(f"/api/v1/tasks/{task_id}").json()
            if task["state"] in {"succeeded", "failed", "cancelled", "lost"}:
                break
            time.sleep(0.05)

    assert task is not None and task["state"] == "succeeded"
    assert Path(task["working_directory"]) == project.resolve()
    assert (project / "generated" / "result.txt").read_text() == str(project.resolve())
    assert not (root / "generated").exists()
