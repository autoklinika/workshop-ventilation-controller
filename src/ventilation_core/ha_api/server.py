from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .app import HaReadOnlyApplication, HaResponse


LOGGER = logging.getLogger(__name__)


class HaApiHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], app: HaReadOnlyApplication) -> None:
        self.app = app
        super().__init__(server_address, HaApiRequestHandler)


class HaApiRequestHandler(BaseHTTPRequestHandler):
    server: HaApiHttpServer

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        self._send(self.server.app.handle("GET", path))

    def do_POST(self) -> None:
        self._reject_write("POST")

    def do_PUT(self) -> None:
        self._reject_write("PUT")

    def do_PATCH(self) -> None:
        self._reject_write("PATCH")

    def do_DELETE(self) -> None:
        self._reject_write("DELETE")

    def do_OPTIONS(self) -> None:
        self._reject_write("OPTIONS")

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info("ha-api %s - %s", self.client_address[0], format % args)

    def _reject_write(self, method: str) -> None:
        path = urlsplit(self.path).path
        self._send(self.server.app.handle(method, path))

    def _send(self, response: HaResponse) -> None:
        encoded = json.dumps(
            response.payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(int(response.status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Allow", "GET")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(encoded)
