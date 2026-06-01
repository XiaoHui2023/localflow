from __future__ import annotations

import argparse

from runtime import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="离线本地 Web 工具：同时提供 React 静态页与 /api 接口",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="监听端口；默认 0 表示随机选择一个空闲端口",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.port < 0 or args.port > 65535:
        raise SystemExit("端口须在 0–65535 之间")
    run_server(port=args.port)


if __name__ == "__main__":
    main()
