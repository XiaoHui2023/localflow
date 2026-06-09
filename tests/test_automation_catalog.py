from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_MAIN = Path(__file__).resolve().parents[1] / "src" / "app_main"


def _load_modules():
    root = str(APP_MAIN)
    if root not in sys.path:
        sys.path.insert(0, root)
    import automation as automation_module
    import automation_catalog as catalog_module

    return catalog_module, automation_module


class AutomationCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog, self.automation = _load_modules()
        self.automation.clear_scripts()
        self.automation.clear_instances()

    def test_lists_automation_scripts_and_handlers(self) -> None:
        am = self.automation

        class DemoScript(am.Script):
            def build_view_template(self):
                return am.text("x")

            def run(self) -> None:
                pass

            def build_result_template(self):
                return am.text("x")

        demo = DemoScript(name="demo", instance_id="bind-demo")
        automation = am.Automation(name="ev_demo")
        automation.register_script(demo)

        @automation.register
        async def on_event(_payload: object) -> None:
            pass

        items = self.catalog.automation_descriptors()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "ev_demo")
        self.assertEqual(items[0]["scripts"][0]["id"], "bind-demo")
        self.assertEqual(items[0]["handlers"][0]["name"], "on_event")


if __name__ == "__main__":
    unittest.main()
