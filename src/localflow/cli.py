from __future__ import annotations

import argparse
import logging
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import uvicorn

from .api import create_app
from .logging_setup import configure_logging
from .settings import initialize_root, load_settings, validate_deployment

logger = logging.getLogger(__name__)


def _endpoint(scheme: str, host: str, port: int) -> str:
    rendered_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"{scheme}://{rendered_host}:{port}"


def _admin_url(endpoint: str, code: str) -> str:
    return f"{endpoint}#{urlencode({'localflow-admin': code})}"


def main() -> None:
    parser = argparse.ArgumentParser(description="LocalFlow Ubuntu offline task platform")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "serve", "status", "login-code", "open"):
        item = sub.add_parser(name)
        item.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if args.command == "init":
        initialize_root(root)
        print(root)
        return
    if args.command == "login-code":
        print((root / "secrets" / "admin-bootstrap").read_text(encoding="ascii").strip())
        return
    if args.command == "status":
        port_file = root / "runtime" / "port"
        print(port_file.read_text(encoding="ascii").strip() if port_file.exists() else "stopped")
        return
    if args.command == "open":
        port_file = root / "runtime" / "port"
        if not port_file.is_file():
            raise SystemExit("LocalFlow is not running")
        endpoint = port_file.read_text(encoding="ascii").strip()
        code = (root / "secrets" / "admin-bootstrap").read_text(encoding="ascii").strip()
        if not webbrowser.open(_admin_url(endpoint, code)):
            raise SystemExit("no graphical browser is available")
        print(endpoint)
        return
    settings = load_settings(root)
    try:
        validate_deployment(settings)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    configure_logging(root, settings.logging)
    logger.info(
        "LocalFlow starting root=%s backend=%s", root, settings.execution.backend
    )
    if settings.execution.backend == "systemd" and os.name != "nt":
        user_runtime = f"/run/user/{os.getuid()}"
        os.environ["XDG_RUNTIME_DIR"] = user_runtime
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={user_runtime}/bus"
    app = create_app(root, settings=settings)
    config = uvicorn.Config(
        app,
        host=settings.server.bind,
        port=settings.server.port,
        log_level="info",
        ssl_certfile=settings.server.tls_certfile,
        ssl_keyfile=settings.server.tls_keyfile,
        forwarded_allow_ips=",".join(settings.server.trusted_proxies),
        log_config=None,
    )
    server = uvicorn.Server(config)
    original_started = server.startup

    async def startup_with_port(sockets=None):
        await original_started(sockets=sockets)
        servers = getattr(server, "servers", [])
        if servers and servers[0].sockets:
            port = servers[0].sockets[0].getsockname()[1]
            port_file = root / "runtime" / "port"
            scheme = "https" if settings.server.tls_certfile else "http"
            port_file.write_text(
                _endpoint(scheme, settings.server.bind, port) + "\n", encoding="ascii"
            )
            if os.name != "nt":
                os.chmod(port_file, 0o600)

    server.startup = startup_with_port
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("LocalFlow stopped")
        port_file = root / "runtime" / "port"
        if port_file.is_file():
            port_file.unlink()


if __name__ == "__main__":
    main()
