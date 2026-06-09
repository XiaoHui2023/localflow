from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

APP_MAIN = Path(__file__).resolve().parents[1] / "src" / "app_main"
REPO = Path(__file__).resolve().parents[1]


def _load(name: str):
    root = str(APP_MAIN)
    if root not in sys.path:
        sys.path.insert(0, root)
    return __import__(name)


class AppConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app_config = _load("app_config")

    def test_load_example_yaml(self) -> None:
        path = REPO / "config.example.yaml"
        cfg = self.app_config.AppConfig.from_file(path)
        self.assertEqual(cfg.port, 0)
        self.assertEqual(cfg.bind_host, "0.0.0.0")
        self.assertEqual(cfg.whitelist, ["127.0.0.1"])

    def test_resolve_relative_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            config_path = config_dir / "app.yaml"
            config_path.write_text(
                "sources:\n  - ../plugins\n",
                encoding="utf-8",
            )
            cfg = self.app_config.AppConfig.from_file(config_path)
            paths = cfg.plugin_paths()
            self.assertEqual(paths, [(config_dir.parent / "plugins").resolve()])

    def test_whitelist_blocks_unknown_ip(self) -> None:
        cfg = self.app_config.AppConfig(whitelist=["127.0.0.1", "10.0.0.5"])
        self.assertTrue(cfg.allows_client("127.0.0.1"))
        self.assertFalse(cfg.allows_client("192.168.1.1"))

    def test_empty_whitelist_allows_all(self) -> None:
        cfg = self.app_config.AppConfig()
        self.assertTrue(cfg.allows_client("192.168.1.1"))


class WhitelistServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server_mod = _load("server")

    def test_server_respects_whitelist(self) -> None:
        httpd = self.server_mod.create_server(
            "127.0.0.1",
            0,
            whitelist=frozenset({"127.0.0.1"}),
        )
        try:
            self.assertTrue(httpd.is_client_allowed("127.0.0.1"))
            self.assertFalse(httpd.is_client_allowed("10.0.0.1"))
        finally:
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
