from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

APP_MAIN = Path(__file__).resolve().parents[1] / "src" / "app_main"


def _load_modules():
    root = str(APP_MAIN)
    if root not in sys.path:
        sys.path.insert(0, root)
    import api as api_module
    import blueprints as blueprint_module

    return api_module, blueprint_module


def _response_body(handler: MagicMock) -> dict:
    raw = handler.wfile.write.call_args[0][0]
    return json.loads(raw.decode("utf-8"))


class BlueprintTest(unittest.TestCase):
    def setUp(self) -> None:
        self.api, self.blueprints = _load_modules()
        self.api._STATE = self.api.AppState()
        self.blueprints.clear_blueprints()

    def test_save_and_list(self) -> None:
        record = self.blueprints.save_blueprint(
            {
                "name": "夜间回归",
                "script_id": "script-1",
                "script_name": "批量",
                "is_batch": True,
                "batch_params": {"seed": "42"},
            },
        )
        self.assertEqual(record["name"], "夜间回归")
        items = self.blueprints.list_blueprints(script_id="script-1")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], record["id"])

    def test_api_create_and_get(self) -> None:
        handler = MagicMock()
        body = {
            "name": "smoke",
            "script_id": "s-1",
            "script_name": "仿真",
            "is_batch": False,
            "variables": {"seed": "1"},
        }
        raw = json.dumps(body).encode("utf-8")
        handler.headers.get.return_value = str(len(raw))
        handler.rfile.read.return_value = raw
        handled = self.api.handle_api(handler, "POST", "/api/blueprints")
        self.assertTrue(handled)
        created = _response_body(handler)
        blueprint_id = created["blueprint"]["id"]

        get_handler = MagicMock()
        handled = self.api.handle_api(get_handler, "GET", f"/api/blueprints/{blueprint_id}")
        self.assertTrue(handled)
        got = _response_body(get_handler)
        self.assertEqual(got["blueprint"]["variables"]["seed"], "1")

    def test_api_delete(self) -> None:
        record = self.blueprints.save_blueprint(
            {
                "name": "tmp",
                "script_id": "s-1",
                "is_batch": False,
                "variables": {},
            },
        )
        handler = MagicMock()
        handled = self.api.handle_api(handler, "DELETE", f"/api/blueprints/{record['id']}")
        self.assertTrue(handled)
        self.assertIsNone(self.blueprints.get_blueprint(record["id"]))


if __name__ == "__main__":
    unittest.main()
