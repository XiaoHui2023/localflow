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


class PluginLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = _load("plugin_loader")
        self.plugin_api = _load("plugin_api")
        clear_instances()
        self.plugin_api.clear_actions()
        _clear_loaded_packages()

    def test_collect_container_and_package(self) -> None:
        repo = self.loader.repo_root()
        dirs = self.loader.collect_plugin_dirs(
            [repo / "plugins", repo / "plugins" / "git_update"],
        )
        names = [d.name for d in dirs]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("git_update", names)
        self.assertGreaterEqual(len(names), 3)

    def test_single_py_source_expands_as_module(self) -> None:
        repo = self.loader.repo_root()
        items = self.loader.collect_load_items(
            [repo / "examples" / "git_watch.py"],
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "module")

    def test_load_plugin_library(self) -> None:
        loaded = self.loader.load_plugins([REPO / "plugins"])
        names = {item.name for item in loaded}
        self.assertGreaterEqual(len(names), 3)
        self.assertIn("git_update", names)
        self.assertIn("plugins.git_update", sys.modules)
        self.assertEqual(len(all_instances()), 0)

    def test_examples_flat_py_module(self) -> None:
        self.loader.load_plugins([REPO / "plugins", REPO / "examples"])
        self.assertIn("examples.git_watch", sys.modules)

    def test_qualified_name_for_single_plugin_path(self) -> None:
        name = self.loader._qualified_name(REPO / "plugins" / "git_update", 0, set())
        self.assertEqual(name, "plugins.git_update")


if __name__ == "__main__":
    unittest.main()
