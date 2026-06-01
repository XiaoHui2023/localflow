from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

APP_MAIN = Path(__file__).resolve().parents[1] / "src" / "app_main"


def _load_api():
    root = str(APP_MAIN)
    if root not in sys.path:
        sys.path.insert(0, root)
    import api as api_module

    return api_module


class ApiRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.api = _load_api()
        self.api._STATE = self.api.AppState()

    def test_status_route(self) -> None:
        handler = MagicMock()
        handled = self.api.handle_api(handler, "GET", "/api/status")
        self.assertTrue(handled)
        handler.wfile.write.assert_called_once()

    def test_unknown_route(self) -> None:
        handler = MagicMock()
        handled = self.api.handle_api(handler, "GET", "/api/unknown")
        self.assertTrue(handled)


if __name__ == "__main__":
    unittest.main()
