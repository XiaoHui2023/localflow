from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

from .api import create_app
from .logging_setup import configure_logging
from .settings import initialize_root, load_settings, validate_deployment

logger = logging.getLogger(__name__)

_INTERNAL_MODE = "LOCALFLOW_INTERNAL_MODE"
_INTERNAL_ROOT = "LOCALFLOW_INTERNAL_ROOT"
_INTERNAL_TASK = "LOCALFLOW_INTERNAL_TASK"
_STARTUP_PROBE = "LOCALFLOW_STARTUP_PROBE"


def _endpoint(scheme: str, host: str, port: int) -> str:
    rendered_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"{scheme}://{rendered_host}:{port}"


def application_root() -> Path:
    """Return the directory that owns this LocalFlow installation."""
    if getattr(sys, "frozen", False):
        executable = os.environ.get("STATICX_PROG_PATH", sys.executable)
        return Path(executable).resolve().parent
    return Path.cwd().resolve()


def _run_internal_mode() -> bool:
    mode = os.environ.get(_INTERNAL_MODE)
    if mode is None:
        return False
    if mode != "supervisor":
        raise SystemExit("invalid LocalFlow internal mode")
    root_text = os.environ.pop(_INTERNAL_ROOT, None)
    task_id = os.environ.pop(_INTERNAL_TASK, None)
    os.environ.pop(_INTERNAL_MODE, None)
    if not root_text or not task_id:
        raise SystemExit("incomplete LocalFlow supervisor environment")
    from .supervisor import supervise

    raise SystemExit(supervise(Path(root_text).resolve(), task_id))


def _serve(root: Path) -> None:
    initialize_root(root)
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
            print(port_file.read_text(encoding="ascii").strip(), flush=True)
            if os.environ.get(_STARTUP_PROBE) == "1":
                server.should_exit = True

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


def main() -> None:
    if sys.argv[1:]:
        raise SystemExit("localflow does not accept arguments; run it directly")
    if _run_internal_mode():
        return
    _serve(application_root())


if __name__ == "__main__":
    main()
