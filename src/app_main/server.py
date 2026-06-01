from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from api import handle_api
from static_files import guess_content_type, resolve_static


class AppHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "masterslave/0.0.0"

    def log_message(self, fmt: str, *args) -> None:
        return

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


def create_server(bind_host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((bind_host, port), AppHTTPRequestHandler)
