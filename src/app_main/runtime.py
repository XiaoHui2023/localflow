from __future__ import annotations

import socket
import sys
from typing import NoReturn

from server import create_server
from static_files import dist_dir


def _local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def print_listen_info(host: str, port: int) -> None:
    lan = _local_lan_ip()
    print(f"服务已监听: {host}:{port}")
    print(f"本机访问: http://127.0.0.1:{port}")
    print(f"局域网访问: http://{lan}:{port}")


def run_server(port: int = 0) -> NoReturn:
    bind_host = "0.0.0.0"
    dist = dist_dir()
    if not dist.is_dir():
        print(
            f"警告: 未找到前端构建目录 {dist}，请先在前端目录执行 npm run build",
            file=sys.stderr,
        )

    httpd = create_server(bind_host, port)
    actual_port = httpd.server_address[1]
    print_listen_info(bind_host, actual_port)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在退出…")
        httpd.server_close()
        raise SystemExit(0) from None
