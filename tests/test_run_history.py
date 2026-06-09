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
    import run_history as run_history_module

    return api_module, run_history_module


def _response_body(handler: MagicMock) -> dict:
    raw = handler.wfile.write.call_args[0][0]
    return json.loads(raw.decode("utf-8"))


class RunHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.api, self.run_history = _load_modules()
        self.api._STATE = self.api.AppState()
        self.run_history.clear_run_history()

    def test_record_and_list(self) -> None:
        script = MagicMock()
        script.describe.return_value = {
            "id": "script-1",
            "name": "仿真",
            "type": "SimRunScript",
            "status": "succeeded",
            "is_batch": False,
            "user_variables": {"seed": "42"},
            "batch_params": None,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00",
            "error": None,
            "error_traceback": None,
            "terminal_log_path": None,
            "result": {"type": "summary", "title": "ok"},
        }
        record = self.run_history.record_from_script(script)
        self.assertIsNotNone(record)
        assert record is not None
        items = self.run_history.list_run_history(script_id="script-1")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], record["id"])
        self.assertEqual(items[0]["status"], "succeeded")

    def test_api_get_history(self) -> None:
        script = MagicMock()
        script.describe.return_value = {
            "id": "s-2",
            "name": "批量",
            "type": "SimBatchScript",
            "status": "failed",
            "is_batch": True,
            "user_variables": {},
            "batch_params": {"cases": ["a"]},
            "started_at": None,
            "finished_at": "2026-01-02T00:00:00+00:00",
            "error": "boom",
            "error_traceback": "trace",
            "terminal_log_path": None,
            "result": None,
        }
        record = self.run_history.record_from_script(script)
        assert record is not None

        list_handler = MagicMock()
        handled = self.api.handle_api(list_handler, "GET", "/api/history")
        self.assertTrue(handled)
        listed = _response_body(list_handler)
        self.assertEqual(len(listed["history"]), 1)

        get_handler = MagicMock()
        handled = self.api.handle_api(get_handler, "GET", f"/api/history/{record['id']}")
        self.assertTrue(handled)
        got = _response_body(get_handler)
        self.assertEqual(got["record"]["batch_params"]["cases"], ["a"])
        self.assertEqual(got["record"]["error"], "boom")


if __name__ == "__main__":
    unittest.main()
