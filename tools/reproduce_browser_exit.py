"""Drive real admin exit through an isolated Selenium browser's public UI."""
from __future__ import annotations

import time

import httpx


class BrowserExit:
    def __init__(self, endpoint: str, key: str, tabs: int):
        self.endpoint, self.key, self.tabs = endpoint, key, tabs
        self.client = httpx.Client(base_url="http://127.0.0.1:4444/wd/hub", timeout=35,
                                   trust_env=False)
        self.session = self.call("POST", "/session", {"capabilities": {"alwaysMatch": {
            "browserName": "chrome", "goog:chromeOptions": {"args": ["--headless", "--no-sandbox"]}
        }}})["sessionId"]

    def call(self, method, path, data=None):
        response = self.client.request(method, path, json=data)
        response.raise_for_status()
        value = response.json()["value"]
        if isinstance(value, dict) and "error" in value:
            raise RuntimeError(f"browser command failed: {value['error']}: {value.get('message', '')}")
        return value

    def command(self, method, path, data=None):
        return self.call(method, f"/session/{self.session}{path}", data)

    def script(self, script, *args):
        return self.command("POST", "/execute/sync", {"script": script, "args": list(args)})

    def wait(self, expression):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.script("return " + expression):
                return
            time.sleep(0.1)
        raise RuntimeError("browser condition timed out: " + expression)

    def click(self, selector):
        element = self.command("POST", "/element", {"using": "css selector", "value": selector})
        identifier = element["element-6066-11e4-a52e-4f735466cecf"]
        self.command("POST", f"/element/{identifier}/click", {})

    def prepare(self):
        self.command("POST", "/timeouts", {"pageLoad": 10000, "script": 10000})
        self.command("POST", "/url", {"url": self.endpoint})
        self.wait("document.querySelector('#root > *') !== null")
        outcome = self.command("POST", "/execute/async", {"script": """
            const done=arguments[arguments.length-1];
            fetch('/api/v1/auth/local-sessions', {method:'POST',
              headers:{'Content-Type':'application/json'}, body:JSON.stringify({key:arguments[0]})})
              .then(r=>done(r.status)).catch(()=>done(0));
        """, "args": [self.key]})
        if outcome != 200:
            raise RuntimeError(f"browser admin login failed: HTTP {outcome}")
        first = self.command("GET", "/window")
        for index in range(self.tabs):
            if index:
                window = self.command("POST", "/window/new", {"type": "tab"})
                self.command("POST", "/window", {"handle": window["handle"]})
            self.command("POST", "/url", {"url": self.endpoint})
            self.wait("document.querySelectorAll('[role=tab]').length >= 3")
            # Allow the real application notification connection to open.
            time.sleep(0.5)
        self.command("POST", "/window", {"handle": first})
        self.click("nav [role=tab]:last-child")
        self.wait("document.querySelector('button.shutdown-trigger') !== null")
        return {"engine": "Chrome84", "tabs": self.tabs, "entry": "actual settings UI"}

    def click_exit(self):
        self.click("button.shutdown-trigger")
        self.wait("document.querySelector('[role=alertdialog]') !== null")
        self.click("[role=alertdialog] button:last-child")

    def close(self):
        try:
            self.command("DELETE", "")
        finally:
            self.client.close()
