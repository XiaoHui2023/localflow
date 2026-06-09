from __future__ import annotations

import asyncio
import socket
import sys
import threading
from pathlib import Path

from automation import run as automation_run, stop as automation_stop
from automation.script.runner import set_script_work_dir
from plugin_loader import load_plugins, repo_root
from server import AppHTTPServer, create_server
from static_files import dist_dir

from app_config import AppConfig


def _local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def print_listen_info(config: AppConfig, port: int) -> None:
    lan = _local_lan_ip()
    print(f"服务已监听: {config.bind_host}:{port}")
    print(f"本机访问: http://127.0.0.1:{port}")
    print(f"局域网访问: http://{lan}:{port}")
    if config.whitelist:
        joined = ", ".join(config.whitelist)
        print(f"IP 白名单: {joined}")


def _start_http_server(
    config: AppConfig,
) -> tuple[AppHTTPServer, threading.Thread, int]:
    dist = dist_dir()
    if not dist.is_dir():
        print(
            f"警告: 未找到前端构建目录 {dist}，请先在前端目录执行 npm run build",
            file=sys.stderr,
        )

    httpd = create_server(
        config.bind_host,
        config.port,
        whitelist=frozenset(config.whitelist),
    )
    actual_port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="localflow-http")
    thread.start()
    return httpd, thread, actual_port


async def _run_automation_service(config: AppConfig) -> None:
    set_script_work_dir(repo_root())
    load_plugins(config.plugin_paths())

    httpd, _thread, actual_port = _start_http_server(config)
    print_listen_info(config, actual_port)

    try:
        await automation_run()
    finally:
        await automation_stop()
        httpd.shutdown()
        httpd.server_close()


def run_app(*, config: AppConfig) -> None:
    try:
        asyncio.run(_run_automation_service(config))
    except KeyboardInterrupt:
        print("\n正在退出…")
        raise SystemExit(0) from None
