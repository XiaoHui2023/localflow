from __future__ import annotations

import argparse
from pathlib import Path

from app_config import AppConfig
from runtime import run_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="本机任务自动化：Web 管理面 + Automation 插件运行时",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="配置文件路径（YAML / JSON / TOML）",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config_path = args.config.expanduser().resolve()
    config = AppConfig.from_file(config_path)
    run_app(config=config)


if __name__ == "__main__":
    main()
