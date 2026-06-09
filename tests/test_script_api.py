from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

APP_MAIN = Path(__file__).resolve().parents[1] / "src" / "app_main"


def _load_modules():
    root = str(APP_MAIN)
    if root not in sys.path:
        sys.path.insert(0, root)
    import api as api_module
    import automation as automation_module

    return api_module, automation_module


def _response_body(handler: MagicMock) -> dict:
    raw = handler.wfile.write.call_args[0][0]
    return json.loads(raw.decode("utf-8"))


class ScriptApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.api, self.automation = _load_modules()
        self.api._STATE = self.api.AppState()
        self.automation.clear_scripts()
        self.automation.clear_instances()

    def test_scripts_route_splits_running_finished(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text("hi")

            def run(self) -> None:
                time.sleep(0.3)

            def build_result_template(self):
                return am.text("done")

        item = DemoScript(name="demo", instance_id="api-demo-1")
        item.start()
        handler = MagicMock()
        handled = self.api.handle_api(handler, "GET", "/api/scripts")
        self.assertTrue(handled)
        body = _response_body(handler)
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["running"]), 1)

    def test_script_variables_patch(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text(am.var_ref("msg"))

            def run(self) -> None:
                pass

            def build_result_template(self):
                return am.text(am.var_ref("msg"))

        DemoScript(name="demo", msg="old", instance_id="api-var-1")
        handler = MagicMock()
        handler.headers.get.return_value = str(
            len(json.dumps({"variables": {"msg": "new"}}).encode("utf-8"))
        )
        handler.rfile.read.return_value = json.dumps({"variables": {"msg": "new"}}).encode(
            "utf-8"
        )
        handled = self.api.handle_api(handler, "PATCH", "/api/scripts/api-var-1/variables")
        self.assertTrue(handled)
        body = _response_body(handler)
        self.assertTrue(body["ok"])
        self.assertEqual(body["script"]["user_variables"]["msg"], "new")
        self.assertEqual(body["script"]["view"]["text"], "new")

    def test_script_start_with_variables(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text(am.var_ref("msg"))

            def run(self) -> None:
                time.sleep(0.05)

            def build_result_template(self):
                return am.text(am.var_ref("msg"))

        DemoScript(name="demo", msg="before", instance_id="api-var-start")
        handler = MagicMock()
        body_json = json.dumps({"variables": {"msg": "launched"}})
        handler.headers.get.return_value = str(len(body_json.encode("utf-8")))
        handler.rfile.read.return_value = body_json.encode("utf-8")
        handled = self.api.handle_api(handler, "POST", "/api/scripts/api-var-start/start")
        self.assertTrue(handled)
        body = _response_body(handler)
        self.assertTrue(body["started"])
        self.assertEqual(body["script"]["user_variables"]["msg"], "launched")

    def test_batch_script_variables_patch(self) -> None:
        from automation import BatchScript, CaseOption, ParamCaseMatrix, ParamText

        class DemoBatch(BatchScript):
            def build_param_schema(self):
                return [
                    ParamText(name="seed", label="种子", default="1"),
                    ParamCaseMatrix(
                        name="cases",
                        label="用例",
                        options=(CaseOption("a", "A", default_enabled=True),),
                    ),
                ]

            def expand_runs(self, params):
                return [{"seed": params["seed"]}] if params["cases"][0]["enabled"] else []

            def create_child_script(self, run_vars):
                class Child(am.Script):
                    def build_view_template(self):
                        return am.text("x")

                    def run(self) -> None:
                        pass

                    def build_result_template(self):
                        return am.text("x")

                return Child(name="c", register=False, **run_vars)

        am = self.automation
        DemoBatch(name="batch", instance_id="api-batch-1")
        body_json = json.dumps({"batch_params": {"seed": "77"}})
        handler = MagicMock()
        handler.headers.get.return_value = str(len(body_json.encode("utf-8")))
        handler.rfile.read.return_value = body_json.encode("utf-8")
        handled = self.api.handle_api(handler, "PATCH", "/api/scripts/api-batch-1/variables")
        self.assertTrue(handled)
        body = _response_body(handler)
        self.assertTrue(body["ok"])
        self.assertEqual(body["script"]["batch_params"]["seed"], "77")

    def test_script_start_route(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text("hi")

            def run(self) -> None:
                time.sleep(0.1)

            def build_result_template(self):
                return am.text("done")

        DemoScript(name="demo", instance_id="api-start-1")
        handler = MagicMock()
        handler.headers.get.return_value = "0"
        handled = self.api.handle_api(handler, "POST", "/api/scripts/api-start-1/start")
        self.assertTrue(handled)
        body = _response_body(handler)
        self.assertTrue(body["started"])

    def test_script_terminal_route(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text("hi")

            def run(self) -> None:
                print("log-line")

            def build_result_template(self):
                return am.text("done")

        item = DemoScript(name="demo", instance_id="api-term-1")
        item.execute()
        handler = MagicMock()
        handled = self.api.handle_api(handler, "GET", "/api/scripts/api-term-1/terminal")
        self.assertTrue(handled)
        body = _response_body(handler)
        self.assertIn("log-line", body["terminal"])

    def test_automations_route(self) -> None:
        am = self.automation
        automation = am.Automation(name="api-auto")

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text("x")

            def run(self) -> None:
                pass

            def build_result_template(self):
                return am.text("x")

        demo = DemoScript(name="demo", instance_id="auto-script-1")
        automation.register_script(demo)

        @automation.register
        async def on_event(_payload: object) -> None:
            pass

        handler = MagicMock()
        handled = self.api.handle_api(handler, "GET", "/api/automations")
        self.assertTrue(handled)
        body = _response_body(handler)
        self.assertTrue(body["ok"])
        self.assertEqual(body["automations"][0]["name"], "api-auto")
        self.assertEqual(body["automations"][0]["scripts"][0]["name"], "demo")

    def test_script_cancel_route(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text("hi")

            def run(self) -> None:
                import sys
                from automation.script.subprocess_cmd import run_shell_command

                cmd = (
                    'python -c "import time; time.sleep(30)"'
                    if sys.platform == "win32"
                    else "sleep 30"
                )
                run_shell_command(self, cmd)

            def build_result_template(self):
                return am.text("done")

        DemoScript(name="demo", instance_id="api-cancel-1")
        start_handler = MagicMock()
        start_handler.headers.get.return_value = "0"
        self.api.handle_api(start_handler, "POST", "/api/scripts/api-cancel-1/start")

        cancel_handler = MagicMock()
        cancel_handler.headers.get.return_value = "2"
        cancel_handler.rfile.read.return_value = b"{}"
        handled = self.api.handle_api(
            cancel_handler,
            "POST",
            "/api/scripts/api-cancel-1/cancel",
        )
        self.assertTrue(handled)
        body = _response_body(cancel_handler)
        self.assertTrue(body["ok"])
        self.assertEqual(body["stage"], "soft")

        force_handler = MagicMock()
        force_handler.headers.get.return_value = "15"
        force_handler.rfile.read.return_value = b'{"force":true}'
        handled = self.api.handle_api(
            force_handler,
            "POST",
            "/api/scripts/api-cancel-1/cancel",
        )
        self.assertTrue(handled)
        force_body = _response_body(force_handler)
        self.assertTrue(force_body["ok"])
        self.assertEqual(force_body["stage"], "hard")

        deadline = time.time() + 5.0
        script = am.get_script("api-cancel-1")
        while time.time() < deadline and script.status.value == "running":
            time.sleep(0.05)
        self.assertEqual(script.status, am.ScriptRunStatus.CANCELLED)

    def test_script_detail_route(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text("hi")

            def run(self) -> None:
                pass

            def build_result_template(self):
                return am.text("done")

        DemoScript(name="demo", instance_id="test-id-001")
        handler = MagicMock()
        handled = self.api.handle_api(handler, "GET", "/api/scripts/test-id-001")
        self.assertTrue(handled)


if __name__ == "__main__":
    unittest.main()
