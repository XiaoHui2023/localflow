from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

APP_MAIN = Path(__file__).resolve().parents[1] / "src" / "app_main"


def _load_automation():
    root = str(APP_MAIN)
    if root not in sys.path:
        sys.path.insert(0, root)
    import automation as automation_module

    return automation_module


class ScriptFrameworkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.automation = _load_automation()
        self.automation.clear_scripts()
        self.automation.clear_instances()

    def test_template_render_resolves_variables(self) -> None:
        tpl = self.automation.div(
            self.automation.summary(
                self.automation.row(
                    self.automation.badge(self.automation.var_ref("project"), tone="primary"),
                    self.automation.text(" / "),
                    self.automation.text(self.automation.var_ref("module")),
                ),
            ),
            self.automation.detail(
                self.automation.labeled("命令", self.automation.var_ref("command")),
            ),
        )
        payload = self.automation.render_template(
            tpl,
            {"project": "chip_a", "module": "tb", "command": "make run"},
        )
        self.assertEqual(payload["kind"], "div")
        summary = payload["children"][0]
        self.assertEqual(summary["kind"], "summary")
        badge_text = summary["children"][0]["children"][0]["text"]
        self.assertEqual(badge_text, "chip_a")

    def test_terminal_log_path_variable_on_init(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text(am.var_ref("terminal_log_path"))

            def run(self) -> None:
                pass

            def build_result_template(self):
                return am.text(am.var_ref("terminal_log_path"))

        item = DemoScript(name="demo", instance_id="path-demo")
        path = item.variables.get("terminal_log_path")
        self.assertIsInstance(path, str)
        self.assertTrue(path.endswith("path-demo.log"))
        self.assertEqual(path, str(item.terminal_log_path))

    def test_script_registers_on_init(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text(am.var_ref("x"))

            def run(self) -> None:
                self.variables.set("x", "done")

            def build_result_template(self):
                return am.text(am.var_ref("x"))

        DemoScript(name="demo", x="init")
        self.assertEqual(len(self.automation.all_scripts()), 1)

    def test_execute_updates_status_and_result(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text(am.var_ref("msg"))

            def run(self) -> None:
                print("hello")
                self.variables.set("msg", "ok")

            def build_result_template(self):
                return am.badge(am.var_ref("msg"), tone="success")

        item = DemoScript(name="demo", msg="pending", instance_id="exec-demo")
        item.execute()
        self.assertEqual(item.status, self.automation.ScriptRunStatus.SUCCEEDED)
        desc = item.describe()
        self.assertEqual(desc["variables"]["msg"], "ok")
        self.assertIsNotNone(desc["result"])
        self.assertEqual(desc["result"]["text"], "ok")
        self.assertIn("hello", desc["terminal"])
        self.assertTrue(desc["terminal_log_path"])

    def test_execute_marks_failed_on_exception(self) -> None:
        am = self.automation

        class FailScript(am.Script):
            def build_view_template(self):
                return am.text("x")

            def run(self) -> None:
                raise RuntimeError("boom")

            def build_result_template(self):
                return am.text("x")

        item = FailScript(name="fail", instance_id="fail-demo")
        with self.assertRaises(RuntimeError):
            item.execute()
        self.assertEqual(item.status, self.automation.ScriptRunStatus.FAILED)
        self.assertEqual(item.describe()["error"], "boom")
        self.assertIn("RuntimeError", item.describe()["error_traceback"])

    def test_start_runs_in_background_thread(self) -> None:
        am = self.automation

        class SlowScript(am.Script):
            def build_view_template(self):
                return am.text("run")

            def run(self) -> None:
                print("thread-run")
                time.sleep(0.2)
                self.variables.set("done", True)

            def build_result_template(self):
                return am.text("done")

        item = SlowScript(name="slow", instance_id="slow-demo")
        self.assertTrue(item.start())
        self.assertFalse(item.start())
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if item.status == am.ScriptRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        self.assertEqual(item.status, am.ScriptRunStatus.SUCCEEDED)
        self.assertIn("thread-run", item.terminal_text())

    def test_running_and_finished_descriptors(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text("x")

            def run(self) -> None:
                pass

            def build_result_template(self):
                return am.text("x")

        idle = DemoScript(name="idle", instance_id="idle-1")
        done = DemoScript(name="done", instance_id="done-1")
        done.status = am.ScriptRunStatus.SUCCEEDED
        running = DemoScript(name="run", instance_id="run-1")
        running.status = am.ScriptRunStatus.RUNNING

        self.assertEqual(len(am.running_script_descriptors()), 1)
        self.assertEqual(len(am.finished_script_descriptors()), 1)
        self.assertEqual(idle.status, am.ScriptRunStatus.IDLE)


if __name__ == "__main__":
    unittest.main()
