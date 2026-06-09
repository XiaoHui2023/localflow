from __future__ import annotations

import sys
import unittest
from pathlib import Path

from automation import all_instances, clear_instances

APP_MAIN = Path(__file__).resolve().parents[1] / "src" / "app_main"
REPO = Path(__file__).resolve().parents[1]


def _load(name: str):
    root = str(APP_MAIN)
    if root not in sys.path:
        sys.path.insert(0, root)
    return __import__(name)


def _clear_loaded_packages() -> None:
    for key in list(sys.modules):
        if key == "plugins" or key.startswith(("plugins.", "examples.")):
            del sys.modules[key]


class ExamplesWiringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = _load("plugin_loader")
        self.plugin_api = _load("plugin_api")
        clear_instances()
        self.plugin_api.clear_actions()
        _clear_loaded_packages()

    def test_plugins_only_no_runtime_registration(self) -> None:
        self.loader.load_plugins([REPO / "plugins"])
        self.assertEqual(len(all_instances()), 0)
        self.assertEqual(self.plugin_api.all_actions(), {})
        self.assertIn("plugins.git_update", sys.modules)

    def test_plugins_then_examples_wires_automation(self) -> None:
        self.loader.load_plugins([REPO / "plugins", REPO / "examples"])
        names = [item.name for item in all_instances()]
        self.assertIn("git_watch", names)
        self.assertIn("git_mail_notify", names)
        self.assertEqual(self.plugin_api.all_actions(), {})
        self.assertIn("plugins.git_update", sys.modules)
        self.assertIn("examples.git_watch", sys.modules)


if __name__ == "__main__":
    unittest.main()
