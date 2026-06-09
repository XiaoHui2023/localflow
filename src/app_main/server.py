from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from api import handle_api
from static_files import guess_content_type, resolve_static


class AppHTTPServer(ThreadingHTTPServer):
    """带客户端 IP 白名单的 HTTP 服务。"""

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        *,
        whitelist: frozenset[str] = frozenset(),
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.whitelist = whitelist

    def is_client_allowed(self, client_ip: str) -> bool:
        if not self.whitelist:
            return True
        return client_ip in self.whitelist


class AppHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "localflow/0.0.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def handle(self) -> None:
        server = self.server
        if isinstance(server, AppHTTPServer) and not server.is_client_allowed(
            self.client_address[0],
        ):
            self.send_error(HTTPStatus.FORBIDDEN, "禁止访问")
            return
        super().handle()

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, url_path: str) -> None:
        file_path = resolve_static(url_path)
        if file_path is None:
            payload = b"frontend/dist not found; run npm run build in frontend/"
            self._send_bytes(HTTPStatus.SERVICE_UNAVAILABLE, payload, "text/plain; charset=utf-8")
            return
        data = file_path.read_bytes()
        self._send_bytes(HTTPStatus.OK, data, guess_content_type(file_path))

    def do_GET(self) -> None:
        if handle_api(self, "GET", self.path):
            return
        self._serve_static(self.path)

    def do_POST(self) -> None:
        if handle_api(self, "POST", self.path):
            return
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "Method Not Allowed")


def create_server(
    bind_host: str,
    port: int,
    *,
    whitelist: frozenset[str] = frozenset(),
) -> AppHTTPServer:
    return AppHTTPServer(
        (bind_host, port),
        AppHTTPRequestHandler,
        whitelist=whitelist,
    )
