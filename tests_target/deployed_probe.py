from __future__ import annotations

import base64
import http.cookiejar
import json
import subprocess
import time
import urllib.request
from pathlib import Path

from localflow.storage import Store

ROOT = Path("/var/lib/localflow")


def endpoint() -> str:
    return (ROOT / "runtime" / "port").read_text(encoding="ascii").strip()


def ready_endpoint() -> str:
    last_error: Exception | None = None
    for _ in range(100):
        try:
            base = endpoint()
            request(opener(), base, "/api/v1/system/status")
            return base
        except Exception as exc:
            last_error = exc
            time.sleep(0.05)
    raise AssertionError(f"service endpoint did not become ready: {last_error}")


def opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def request(
    browser: urllib.request.OpenerDirector,
    base: str,
    path: str,
    body: dict | None = None,
    method: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    method = method or ("POST" if body is not None else "GET")
    call = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={
            **({"Content-Type": "application/json"} if data else {}),
            **(headers or {}),
        },
    )
    with browser.open(call, timeout=10) as response:
        return json.load(response)


def login(base: str) -> urllib.request.OpenerDirector:
    browser = opener()
    key = (ROOT / "secrets" / "web-admin-key").read_text(encoding="ascii").strip()
    result = request(browser, base, "/api/v1/auth/local-sessions", {"key": key})
    assert result["role"] == "admin"
    browser.addheaders = [
        ("Origin", base),
        ("X-CSRF-Token", result["csrf_token"]),
    ]
    return browser


def main() -> None:
    first_base = ready_endpoint()
    anonymous = opener()
    with anonymous.open(first_base + "/", timeout=10) as page:
        assert b'<div id="root"></div>' in page.read()
    status = request(anonymous, first_base, "/api/v1/system/status")
    assert status["role"] == "summary"

    admin = login(first_base)
    created = request(
        admin,
        first_base,
        "/api/v1/tasks",
        {
            "name": "deployed-restart",
            "working_directory": "/var/lib/localflow",
            "command": ["/bin/sh", "-c", "sleep 5; printf deployment-survived"],
            "labels": ["target", "restart"],
        },
    )
    task_id = created["task_id"]
    for _ in range(100):
        task = request(admin, first_base, f"/api/v1/tasks/{task_id}")
        if task["state"] == "running":
            break
        time.sleep(0.05)
    if task["state"] != "running":
        store = Store(ROOT / "runtime" / "localflow.db")
        diagnostics = [event.model_dump(mode="json") for event in store.events_after(0)]
        store.close()
        raise AssertionError({"task": task, "events": diagnostics[-10:]})

    subprocess.run(["systemctl", "restart", "localflow.service"], check=True)
    for _ in range(100):
        try:
            second_base = endpoint()
            new_admin = login(second_base)
            break
        except Exception:
            time.sleep(0.05)
    else:
        raise AssertionError("service did not return after restart")

    for _ in range(200):
        task = request(new_admin, second_base, f"/api/v1/tasks/{task_id}")
        if task["state"] in {"succeeded", "failed", "cancelled", "lost"}:
            break
        time.sleep(0.05)
    assert task["state"] == "succeeded", task
    log = request(new_admin, second_base, f"/api/v1/tasks/{task_id}/logs")
    assert b"deployment-survived" in base64.b64decode(log["data"])

    summary = request(anonymous, second_base, f"/api/v1/tasks/{task_id}")
    assert "command" not in summary and "working_directory" not in summary

    config = request(new_admin, second_base, "/api/v1/config/files/server.yaml")
    fixed_port = 38473
    fixed_content = config["content"].replace("port: 0", f"port: {fixed_port}")
    assert fixed_content != config["content"]
    request(
        new_admin,
        second_base,
        "/api/v1/config/files/server.yaml",
        {"content": fixed_content},
        method="PUT",
        headers={"If-Match": config["version"]},
    )
    subprocess.run(["systemctl", "restart", "localflow.service"], check=True)
    for _ in range(100):
        try:
            fixed_base = endpoint()
            if fixed_base.endswith(f":{fixed_port}"):
                fixed_admin = login(fixed_base)
                break
        except Exception:
            pass
        time.sleep(0.05)
    else:
        raise AssertionError("fixed port was not applied")

    fixed_config = request(fixed_admin, fixed_base, "/api/v1/config/files/server.yaml")
    request(
        fixed_admin,
        fixed_base,
        "/api/v1/config/files/server.yaml",
        {"content": fixed_config["content"].replace(f"port: {fixed_port}", "port: 0")},
        method="PUT",
        headers={"If-Match": fixed_config["version"]},
    )
    print(
        json.dumps(
            {
                "task_id": task_id,
                "first_endpoint": first_base,
                "second_endpoint": second_base,
                "state": task["state"],
                "fixed_endpoint": fixed_base,
                "anonymous_fields": sorted(summary),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
