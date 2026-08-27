from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import psutil
import yaml
from configlib import load_config_raw
from run_linux_browser_quality import LEGACY_BROWSERS, run_legacy_browser

from localflow.settings import initialize_root

REPOSITORY = Path(__file__).resolve().parents[1]


def measure_idle_server(
    process: subprocess.Popen[str], root: Path
) -> dict[str, float | int | bool]:
    """Measure only the fresh LocalFlow controller; task processes are forbidden."""
    contract = json.loads(
        (REPOSITORY / "quality" / "resource-budgets.json").read_text(encoding="utf-8")
    )
    measurement = contract["measurement"]
    time.sleep(measurement["server_warmup_seconds"])
    controller = psutil.Process(process.pid)
    database = sqlite3.connect(root / "runtime" / "localflow.db")
    try:
        task_process_count = database.execute(
            "SELECT count(*) FROM tasks WHERE state NOT IN ('succeeded','failed','cancelled','lost')"
        ).fetchone()[0]
    finally:
        database.close()
    if task_process_count:
        raise RuntimeError(f"idle resource gate found {task_process_count} active tasks")
    service_processes = [controller, *controller.children(recursive=True)]
    before = {
        item.pid: item.cpu_times().user + item.cpu_times().system for item in service_processes
    }
    started = time.monotonic()
    rss_samples: list[int] = []
    deadline = started + measurement["idle_window_seconds"]
    while time.monotonic() < deadline:
        service_processes = [controller, *controller.children(recursive=True)]
        rss_samples.append(sum(item.memory_info().rss for item in service_processes))
        time.sleep(measurement["server_sample_interval_seconds"])
    elapsed = time.monotonic() - started
    after = {
        item.pid: item.cpu_times().user + item.cpu_times().system
        for item in [controller, *controller.children(recursive=True)]
    }
    cpu_seconds = sum(after.get(pid, started_at) - started_at for pid, started_at in before.items())
    return {
        "task_process_count": task_process_count,
        "service_process_count": len(after),
        "idle_window_seconds": round(elapsed, 3),
        "server_rss_mib": round(max(rss_samples) / (1024 * 1024), 3),
        "server_cpu_one_core_percent": round(cpu_seconds / elapsed * 100, 3),
    }


def wait_for_server(root: Path, process: subprocess.Popen[str]) -> str:
    port_file = root / "runtime" / "port"
    deadline = time.monotonic() + 30
    last_error = "port file not written"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"LocalFlow exited before readiness with {process.returncode}")
        if port_file.is_file():
            url = port_file.read_text(encoding="ascii").strip()
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        return url
            except OSError as exc:
                last_error = str(exc)
        time.sleep(0.1)
    raise TimeoutError(f"LocalFlow did not become ready: {last_error}")


def main() -> int:
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is required for the browser quality gate")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("docker is required for fixed-version browser testing")
    frontend = REPOSITORY / "frontend"
    evidence = REPOSITORY / "quality" / "evidence" / "browser"
    evidence.mkdir(parents=True, exist_ok=True)
    for name in (
        "anonymous-settings-login-light.png",
        "anonymous-settings-login-mobile.png",
        "admin-empty-light.png",
        "admin-task-detail-dark.png",
        "admin-api-light.png",
        "admin-settings-light.png",
        "admin-run-dark.png",
        "admin-task-detail.png",
        "admin-template-cases.png",
        "admin-config-monaco.png",
        "admin-mobile-390.png",
        "admin-terminal-dark.png",
        "admin-plugins-dark.png",
        "admin-run-verification-dark.png",
        "admin-run-verification-empty-dark.png",
        "admin-run-verification-scope-dark.png",
        "browser-receipt.json",
    ):
        target = evidence / name
        if target.is_file():
            target.unlink()

    subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    with tempfile.TemporaryDirectory(prefix="localflow-browser-qa-") as temporary:
        root = Path(temporary) / "root"
        initialize_root(root)
        settings_path = root / "config" / "server.yaml"
        settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
        settings["execution"].update(
            {
                "backend": "subprocess",
                "max_concurrency": 1,
                "sigint_grace_seconds": 0.2,
                "sigterm_grace_seconds": 0.2,
            }
        )
        settings_path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
        for name in ("marker-warning.yaml", "verification-demo.yaml"):
            task_path = root / "config" / "tasks" / name
            task = load_config_raw(task_path)
            task["command"][0] = sys.executable
            task_path.write_text(
                yaml.safe_dump(task, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
        (root / "qa-cases" / "case-a").mkdir(parents=True)
        (root / "qa-cases" / "case-b").mkdir(parents=True)
        (root / "config" / "tasks" / "qa-invalid.yaml").write_text(
            "plugin: command\nlabels: wrong\n", encoding="utf-8"
        )
        (root / "plugins" / "generic_picker.py").write_text(
            """from pydantic import BaseModel, ConfigDict, Field
from localflow.models import TaskCreate
from localflow.plugins import plugin, run_field

class GenericPickerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_directory: str
    jobs: list[str] = Field(default_factory=list)
    default_repeats: int = Field(default=1, ge=1)
    job_repeats: dict[str, int] = Field(default_factory=dict)

@plugin("generic-picker")
class GenericPicker:
    config_model = GenericPickerConfig
    required_common_fields = {"command"}
    title = "通用选择器质检"
    example = {
        "plugin": "generic-picker",
        "job_directory": "${root}/qa-cases",
        "command": ["python3", "-c", "pass"],
    }
    api_inputs = {"jobs": ["case-a"], "job_repeats": {"case-a": 1}}
    run_fields = [run_field(
        "jobs", "case-picker", required=True, multiple=True, label="Job",
        count_field="job_repeats", default_count_field="default_repeats",
    )]

    def discover(self, values, _context):
        from pathlib import Path
        return sorted(path.name for path in Path(values["job_directory"]).iterdir())

    def expand(self, values, context):
        tasks = []
        for job in values.get("jobs", []):
            repeats = values.get("job_repeats", {}).get(job, values.get("default_repeats", 1))
            for index in range(int(repeats)):
                tasks.append(TaskCreate(
                    name=f"{job} generic #{index + 1}",
                    working_directory=context["root"],
                    command=list(values["command"]),
                    labels=["generic-picker", job],
                ))
        if not tasks:
            raise ValueError("at least one job is required")
        return tasks
""",
            encoding="utf-8",
        )
        (root / "config" / "tasks" / "generic-picker.yaml").write_text(
            yaml.safe_dump(
                {
                    "plugin": "generic-picker",
                    "job_directory": "${root}/qa-cases",
                    "command": [sys.executable, "-c", "pass"],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["LOCALFLOW_WEB_DIST"] = str(frontend / "dist")
        process = subprocess.Popen(
            [sys.executable, "-m", "localflow.cli"],
            cwd=root,
            env=environment,
            text=True,
        )
        try:
            url = wait_for_server(root, process)
            server_resources = measure_idle_server(process, root)
            admin_key = (root / "secrets" / "web-admin-key").read_text(
                encoding="ascii"
            ).strip()
            qa_environment = environment.copy()
            qa_environment.update(
                {
                    "LOCALFLOW_QA_URL": url,
                    "LOCALFLOW_QA_ROOT": str(root),
                    "LOCALFLOW_QA_PYTHON": sys.executable,
                    "LOCALFLOW_QA_ADMIN_KEY": admin_key,
                    "LOCALFLOW_QA_SERVER_RESOURCES": json.dumps(server_resources),
                }
            )
            result = subprocess.run(
                [npm, "run", "test:e2e"],
                cwd=frontend,
                env=qa_environment,
                check=False,
            )
            if result.returncode:
                return result.returncode
            compatibility = subprocess.run(
                [npm, "run", "test:compat"],
                cwd=frontend,
                env=qa_environment,
                check=False,
            )
            if compatibility.returncode:
                return compatibility.returncode
            legacy_environment = {
                **qa_environment,
                "LOCALFLOW_COMPAT_EVIDENCE": str(
                    REPOSITORY / "quality" / "evidence" / "browser-fixed"
                ),
            }
            for project, image, browser in LEGACY_BROWSERS:
                result = run_legacy_browser(
                    docker=docker,
                    npm=npm,
                    image=image,
                    browser=browser,
                    project=project,
                    environment=legacy_environment,
                )
                if result:
                    return result
            return 0
        finally:
            if os.name == "nt" and process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if os.name == "nt":
                database_path = root / "runtime" / "localflow.db"
                for _ in range(20):
                    try:
                        database_path.unlink(missing_ok=True)
                        break
                    except PermissionError:
                        time.sleep(0.1)


if __name__ == "__main__":
    raise SystemExit(main())
