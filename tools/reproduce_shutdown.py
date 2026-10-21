"""Exercise public shutdown with real Linux processes in a disposable instance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import psutil
import yaml

from localflow.paths import initialize_state_root
from localflow.settings import initialize_config_root


def identity(pid: int) -> dict | None:
    try:
        process = psutil.Process(pid)
        status = process.status()
        return {"pid": pid, "created": process.create_time(), "status": status,
                "argv": [] if status == psutil.STATUS_ZOMBIE else process.cmdline()}
    except psutil.NoSuchProcess:
        return None


def same_process(expected: dict | None) -> bool:
    if expected is None:
        return False
    current = identity(expected["pid"])
    return current is not None and current["created"] == expected["created"]


def wait_until(check, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return bool(check())


def probe(backend: str, scenario: str, budget: float, output: Path,
          binary: Path | None = None, browser_tabs: int = 0) -> dict:
    if sys.platform != "linux":
        raise RuntimeError("this public-process probe requires Linux")
    temporary = tempfile.TemporaryDirectory(prefix="localflow-exit-probe-")
    directory = Path(temporary.name)
    workspace, state = directory / "workspace", directory / "state"
    initialize_config_root(workspace)
    initialize_state_root(state)
    configuration = yaml.safe_load((workspace / "config.yaml").read_text())
    configuration["server"].update(bind="127.0.0.1", port=0)
    configuration["execution"].update(
        backend=backend, sigint_grace_seconds=0.15, sigterm_grace_seconds=0.15
    )
    configuration.setdefault("logging", {})["keep_free_mb"] = 0
    (workspace / "config.yaml").write_text(yaml.safe_dump(configuration))
    log_path = directory / "controller.log"
    child_file = directory / "child.pid"
    controller_argv = ([str(binary)] if binary else [sys.executable, "-m", "localflow.cli"])
    controller_argv += ["--workspace", str(workspace), "--data", str(state)]
    with log_path.open("wb") as stream:
        controller = subprocess.Popen(
            controller_argv, stdout=stream, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    controller_identity = identity(controller.pid)
    child_identity = None
    task_id = None
    unit = None
    result = {"backend": backend, "scenario": scenario, "controller": controller_identity,
              "argv": controller_argv, "budget_seconds": budget, "natural_entry": True}
    client = None
    browser = None
    try:
        port_file = state / "runtime" / "port"
        if not wait_until(lambda: port_file.exists() or controller.poll() is not None, 20):
            raise RuntimeError("controller startup timed out")
        if not port_file.exists():
            raise RuntimeError("controller exited before exposing its endpoint")
        endpoint = port_file.read_text().strip()
        result["endpoint"] = endpoint
        pid_file = state / "runtime" / "localflow.pid"
        if not wait_until(pid_file.exists, 3):
            raise RuntimeError("application identity receipt is missing")
        application_identity = identity(int(pid_file.read_text()))
        result["application"] = application_identity
        client = httpx.Client(base_url=endpoint, timeout=3, trust_env=False)
        key = (workspace / "secrets" / "web-admin-key").read_text().strip()
        response = client.post("/api/v1/auth/local-sessions", json={"key": key})
        response.raise_for_status()
        client.headers.update({"Origin": endpoint, "X-CSRF-Token": response.json()["csrf_token"]})
        if scenario != "idle":
            if scenario in {"running", "stop_helper"}:
                command = [sys.executable, "-c", "import time; time.sleep(120)"]
            else:
                child = (
                    "import os,time,signal; from pathlib import Path; "
                    "signal.signal(signal.SIGINT,signal.SIG_IGN); "
                    "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                    f"Path({str(child_file)!r}).write_text(str(os.getpid())); time.sleep(120)"
                )
                command = [sys.executable, "-c",
                           "import subprocess,time; "
                           f"subprocess.Popen([{sys.executable!r},'-c',{child!r}],"
                           f"start_new_session={scenario == 'detached_child'}); time.sleep(0.5)"]
            task_input = {
                "name": "exit-probe", "working_directory": str(directory), "command": command,
                "stop": {"actions": [
                    {"type": "signal", "signal": "SIGINT", "timeout_seconds": 0.15},
                    {"type": "signal", "signal": "SIGTERM", "timeout_seconds": 0.15},
                ]},
            }
            if scenario == "stop_helper":
                helper = ("import os,time; from pathlib import Path; "
                          f"Path({str(child_file)!r}).write_text(str(os.getpid())); time.sleep(120)")
                task_input["stop"] = {"actions": [{"type": "exec", "command": [
                    sys.executable, "-c", helper], "timeout_seconds": 120}]}
            input_bytes = json.dumps(task_input, sort_keys=True).encode()
            result["input_sha256"] = hashlib.sha256(input_bytes).hexdigest()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_suffix(".input.json").write_bytes(input_bytes)
            created = client.post("/api/v1/tasks", json=task_input)
            created.raise_for_status()
            task_id = created.json()["task_id"]
            result["task_id"] = task_id

            def task_started() -> bool:
                detail = client.get(f"/api/v1/tasks/{task_id}")
                detail.raise_for_status()
                return detail.json()["state"] not in {"queued", "starting"}

            if not wait_until(task_started, 15):
                raise RuntimeError("task did not reach execution")
            if scenario not in {"running", "stop_helper"}:
                if not wait_until(child_file.exists, 10):
                    raise RuntimeError("the public task did not produce its child identity")
                child_identity = identity(int(child_file.read_text()))
                if child_identity is None or str(child_file) not in " ".join(child_identity["argv"]):
                    raise RuntimeError("child identity is not bound to this disposable run")
                result["child"] = child_identity
                parent_identity = identity(psutil.Process(child_identity["pid"]).ppid())
                if not wait_until(lambda: not same_process(parent_identity), 4):
                    raise RuntimeError("task parent did not finish the public child-launch command")
            descriptor = state / "runtime" / "instances" / f"{task_id}.json"
            if descriptor.exists():
                unit = json.loads(descriptor.read_text()).get("_localflow", {}).get("unit")
            result["task_before_shutdown"] = client.get(f"/api/v1/tasks/{task_id}").json()["state"]
        if browser_tabs:
            from reproduce_browser_exit import BrowserExit
            browser = BrowserExit(endpoint, key, browser_tabs)
            result["browser"] = browser.prepare()
        started = time.monotonic()
        if browser:
            browser.click_exit()
            result["browser_exit_clicked"] = True
        else:
            accepted = client.post("/api/v1/system/shutdown")
            result["shutdown_http_status"] = accepted.status_code
            accepted.raise_for_status()
        if scenario == "stop_helper":
            if not wait_until(child_file.exists, 5):
                raise RuntimeError("stop helper did not start through public shutdown")
            child_identity = identity(int(child_file.read_text()))
            result["stop_helper"] = child_identity
        exited = wait_until(lambda: controller.poll() is not None, budget)
        result.update({
            "controller_exited": exited,
            "application_still_running": same_process(application_identity),
            "controller_exit_code": controller.poll(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "child_still_running": same_process(child_identity),
            "port_file_present": port_file.exists(),
            "pid_file_present": (state / "runtime" / "localflow.pid").exists(),
        })
        result["passed"] = (exited and controller.returncode == 0
                            and not result["child_still_running"] and not result["application_still_running"]
                            and not result["port_file_present"] and not result["pid_file_present"])
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error), passed=False)
    finally:
        if client:
            client.close()
        try:
            # Preserve the observed outcome before reclaiming only this probe's resources.
            output.parent.mkdir(parents=True, exist_ok=True)
            if log_path.exists():
                data = log_path.read_bytes()
                output.with_suffix(".controller.log").write_bytes(data)
                result["controller_log_sha256"] = hashlib.sha256(data).hexdigest()
            output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        finally:
            if browser:
                try:
                    browser.close()
                except Exception as error:
                    result["browser_cleanup_error"] = str(error)
            if unit and task_id and unit.endswith(f"-task-{task_id}.service"):
                subprocess.run(["systemctl", "--user", "kill", "--kill-whom=all", "--signal=SIGKILL", unit],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                subprocess.run(["systemctl", "--user", "stop", "--no-block", unit],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if same_process(child_identity):
                os.kill(child_identity["pid"], signal.SIGKILL)
            if same_process(controller_identity):
                os.killpg(controller.pid, signal.SIGKILL)
            controller.wait(timeout=5)
            clean = wait_until(lambda: not same_process(child_identity), 5)
            try:
                output.with_suffix(".cleanup.json").write_text(json.dumps({
                    "controller_reaped": controller.poll() is not None, "child_gone": clean,
                }, indent=2), encoding="utf-8")
            finally:
                temporary.cleanup()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("auto", "subprocess", "systemd"), required=True)
    parser.add_argument("--scenario", choices=("idle", "running", "group_child", "detached_child", "stop_helper"), required=True)
    parser.add_argument("--budget", type=float, default=18)
    parser.add_argument("--expect", choices=("clean", "reproduced"), default="clean")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--browser-tabs", type=int, default=0)
    args = parser.parse_args()
    result = probe(args.backend, args.scenario, args.budget, args.output, args.binary, args.browser_tabs)
    print(json.dumps(result))
    reproduced = ((result.get("shutdown_http_status") == 202 or result.get("browser_exit_clicked"))
                  and not result["passed"] and "error" not in result)
    return 0 if (result["passed"] if args.expect == "clean" else reproduced) else 1


if __name__ == "__main__":
    raise SystemExit(main())
