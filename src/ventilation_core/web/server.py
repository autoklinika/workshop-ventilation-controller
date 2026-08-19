from __future__ import annotations

import json
import logging
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .app import ApiResponse, WebApplication


LOGGER = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 64 * 1024


class WebUiHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], app: WebApplication, static_root: Path) -> None:
        self.app = app
        self.static_root = static_root.resolve()
        super().__init__(server_address, WebUiRequestHandler)


class WebUiRequestHandler(BaseHTTPRequestHandler):
    server: WebUiHttpServer

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            self._send_api(self.server.app.handle("GET", path))
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if not path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            self._send_json(HTTPStatus.LENGTH_REQUIRED, {"ok": False, "error": "Content-Length required"})
            return
        try:
            length = int(length_header)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid Content-Length"})
            return
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "Request body too large"})
            return
        raw = self.rfile.read(length)
        if raw:
            try:
                body: Any = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid JSON body"})
                return
        else:
            body = {}
        self._send_api(self.server.app.handle("POST", path, body))

    def do_PUT(self) -> None: self._method_not_allowed()
    def do_DELETE(self) -> None: self._method_not_allowed()
    def do_PATCH(self) -> None: self._method_not_allowed()

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info("web-ui %s - %s", self.client_address[0], format % args)

    def _method_not_allowed(self) -> None:
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "Method not allowed"})

    def _send_api(self, response: ApiResponse) -> None:
        self._send_json(response.status, response.payload)

    def _send_json(self, status: int | HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_static(self, request_path: str) -> None:
        if request_path in (
            "", "/", "/control", "/control/", "/alerts", "/alerts/", "/settings", "/settings/"
        ):
            relative = "index.html"
        else:
            relative = request_path.lstrip("/")
        allowed = {
            "index.html", "control.html", "settings.html", "styles.css", "dashboard.css", "ai-detail.css", "zone-detail.css", "sidebar.css", "v2-weather.css",
            "cm5-watchdog.css", "schedule.css", "zigbee-settings.css", "zigbee-stage13.css",
            "dashboard.js", "dashboard-live.js", "ai-operator-view.js", "zone-detail.js", "cm5-watchdog.js", "app.js", "tacho.js", "alerts.js", "schedule.js", "zigbee-settings.js",
        }
        if relative not in allowed:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        candidate = (self.server.static_root / relative).resolve()
        if candidate.parent != self.server.static_root or not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = candidate.read_bytes()

        # The dashboard already loads the Stage 2 AI assets. Keep the zone-detail
        # implementation in separate source files, but append those presentation-only
        # modules to the existing dashboard asset responses so no legacy HTML shell
        # rewrite is required while the V2 GUI remains under staged development.
        if relative == "ai-operator-view.js":
            zone_js = (self.server.static_root / "zone-detail.js").resolve()
            if zone_js.parent == self.server.static_root and zone_js.is_file():
                content += b"\n\n" + zone_js.read_bytes()
        elif relative == "ai-detail.css":
            zone_css = (self.server.static_root / "zone-detail.css").resolve()
            if zone_css.parent == self.server.static_root and zone_css.is_file():
                content += b"\n\n" + zone_css.read_bytes()

        content_type, _ = mimetypes.guess_type(candidate.name)
        if content_type is None:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(content)

    def _send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
