"""Exercise a final Linux executable using only the target's Python standard library."""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def until(check, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise RuntimeError("bounded recovery condition did not converge")


class Instance:
    def __init__(self, binary, root):
        self.binary, self.root = binary, root
        self.workspace, self.state = root / "workspace", root / "state"
        self.workspace.mkdir()
        config = {
            "server": {"bind": "127.0.0.1", "port": 0},
            "execution": {"backend": "systemd", "sigint_grace_seconds": 0.1,
                          "sigterm_grace_seconds": 0.1},
            "logging": {"keep_free_mb": 0},
        }
        (self.workspace / "config.yaml").write_text(json.dumps(config))
        self.process = None
        self.pid = None
        self.units = set()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )
        self.headers = {}

    def request(self, path, data=None):
        headers = {**self.headers}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.url + path, headers=headers,
            data=json.dumps(data).encode() if data is not None else None,
        )
        with self.opener.open(request, timeout=3) as response:
            return json.load(response)

    def launch(self):
        previous = self.pid
        self.headers = {}
        log = (self.root / f"controller-{time.time_ns()}.log").open("wb")
        try:
            self.process = subprocess.Popen(
                [str(self.binary), "--workspace", str(self.workspace), "--data", str(self.state)],
                stdout=log, stderr=subprocess.STDOUT,
            )
        finally:
            log.close()

        def ready():
            if self.process.poll() is not None:
                raise RuntimeError("controller exited during recovery")
            pid, port = self.state / "runtime/localflow.pid", self.state / "runtime/port"
            if not pid.exists() or not port.exists():
                return False
            current = int(pid.read_text())
            if current == previous:
                return False
            self.url = port.read_text().strip()
            try:
                self.request("/api/v1/system/status")
                session = self.request("/api/v1/auth/local-sessions", {
                    "key": (self.workspace / "secrets/web-admin-key").read_text().strip(),
                })
                self.headers = {"Origin": self.url, "X-CSRF-Token": session["csrf_token"]}
                self.pid = current
                return True
            except (OSError, urllib.error.URLError):
                return False

        until(ready)

    def submit(self, tail=False):
        command = ["/usr/bin/python3", "-u", "-c",
                   "import signal,time;signal.signal(signal.SIGINT,signal.SIG_IGN);"
                   "signal.signal(signal.SIGTERM,signal.SIG_IGN);print('TASK_READY',flush=True);"
                   "time.sleep(300)"]
        if tail:
            child = ("import os,signal,time;from pathlib import Path;"
                     "signal.signal(signal.SIGINT,signal.SIG_IGN);"
                     "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                     "signal.signal(signal.SIGHUP,signal.SIG_IGN);"
                     f"Path({str(self.root / 'tail.pid')!r}).write_text(str(os.getpid()));"
                     "time.sleep(300)")
            command = ["/usr/bin/python3", "-u", "-c",
                       "import subprocess,time;from pathlib import Path;"
                       f"subprocess.Popen(['/usr/bin/python3','-u','-c',{child!r}]);"
                       f"p=Path({str(self.root / 'tail.pid')!r});"
                       "exec('while not p.exists(): time.sleep(.01)');print('TASK_READY',flush=True)"]
        key = self.request("/api/v1/tasks", {
            "name": "crash-recovery-probe", "command": command,
            "working_directory": str(self.root),
        })["task_id"]
        log = self.state / "logs" / key / "output.log"
        until(lambda: log.exists() and "TASK_READY" in log.read_text(errors="replace"))
        until(lambda: bool(self.request("/api/v1/tasks/" + key)["executor_ref"]))
        task = self.request("/api/v1/tasks/" + key)
        self.units.add(task["executor_ref"])
        return key, task["executor_ref"]

    def control(self, unit, command="kill"):
        argv = ["systemctl", "--user", command]
        if command == "kill":
            argv += ["--kill-who=all", "--signal=SIGKILL"]
        return subprocess.run([*argv, unit], capture_output=True, timeout=10)

    def crash(self):
        os.kill(self.pid, signal.SIGKILL)
        self.process.wait(timeout=10)

    def shutdown(self):
        self.request("/api/v1/system/shutdown", {})
        if self.process.wait(timeout=20) != 0:
            raise AssertionError("controller did not exit normally")
        assert not (self.state / "runtime/localflow.pid").exists()
        assert not (self.state / "runtime/port").exists()

    def cleanup(self):
        # Fixture cleanup is deliberately later than all product assertions.
        try:
            for unit in self.units:
                if unit:
                    self.control(unit)
        finally:
            if self.process is not None and self.process.poll() is None:
                try:
                    self.shutdown()
                except (OSError, RuntimeError, AssertionError, subprocess.TimeoutExpired):
                    self.crash()


def probe(binary, scenario, output):
    evidence = {"scenario": scenario, "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "systemd_version": subprocess.check_output(["systemctl", "--version"], text=True).splitlines()[0],
                "real_kernel_reboot": False}
    with tempfile.TemporaryDirectory(prefix="lf-recovery-") as folder:
        instance = Instance(binary, Path(folder))
        try:
            instance.launch()
            key, unit = instance.submit(tail=scenario == "tail")
            if scenario == "tail":
                until(lambda: (instance.state / "runtime/instances" / f"{key}.exit").exists())
            if scenario == "stop":
                instance.request(f"/api/v1/tasks/{key}/interrupt", {})
                until(lambda: instance.request(f"/api/v1/tasks/{key}")["state"] == "cancelled", 8)
                evidence["state"] = "cancelled"
            else:
                instance.crash()
                if scenario in {"cold", "boot"}:
                    instance.control(unit)
                    until(lambda: subprocess.run(
                        ["systemctl", "--user", "is-active", "--quiet", unit],
                        capture_output=True, timeout=3,
                    ).returncode != 0)
                if scenario == "boot":
                    # Inject a previous-boot receipt and a genuinely reused unit.
                    # This proves startup identity handling, not a physical power cycle.
                    marker = instance.state / "runtime/host-boot.json"
                    marker.write_text(json.dumps({"version": 1,
                                                 "boot_id": "00000000-0000-4000-8000-000000000000"}))
                    subprocess.run(["systemctl", "--user", "reset-failed", unit], capture_output=True)
                    until(lambda: b"LoadState=not-found" in subprocess.run(
                        ["systemctl", "--user", "show", "--property=LoadState", unit],
                        capture_output=True, timeout=3,
                    ).stdout)
                    subprocess.run(["systemd-run", "--user", "--unit", unit, "--quiet",
                                    "/bin/sleep", "300"], check=True, capture_output=True)
                instance.launch()
                task = instance.request(f"/api/v1/tasks/{key}")
                evidence["state"] = task["state"]
                expected = "running" if scenario in {"survive", "tail"} else "lost"
                assert task["state"] == expected, task
                if scenario == "survive":
                    instance.request(f"/api/v1/tasks/{key}/interrupt", {})
                    until(lambda: instance.request(f"/api/v1/tasks/{key}")["state"] == "cancelled", 8)
                elif scenario == "tail":
                    instance.control(unit)
                    until(lambda: instance.request(f"/api/v1/tasks/{key}")["state"] == "succeeded", 8)
                    child = int((instance.root / "tail.pid").read_text())
                    until(lambda: not Path(f"/proc/{child}").exists())
            if scenario != "boot":
                assert subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit],
                                      capture_output=True).returncode != 0
            instance.shutdown()
            if scenario == "boot":
                assert subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit],
                                      capture_output=True).returncode == 0
                evidence["reused_unit_preserved"] = True
            evidence["product_assertions_before_cleanup"] = True
            evidence["passed"] = True
        except Exception as exc:
            evidence.update(passed=False, error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            output.parent.mkdir(parents=True, exist_ok=True)
            for log in Path(folder).glob("controller-*.log"):
                output.with_suffix("." + log.name).write_bytes(log.read_bytes())
            try:
                instance.cleanup()
            finally:
                output.write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--scenario", choices=["stop", "cold", "survive", "boot", "tail"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    probe(args.binary.resolve(), args.scenario, args.output.resolve())
