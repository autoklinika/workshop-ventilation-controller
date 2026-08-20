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
            "", "/", "/control", "/control/", "/alerts", "/alerts/", "/settings", "/settings/", "/history", "/history/", "/service", "/service/"
        ):
            relative = "index.html"
        else:
            relative = request_path.lstrip("/")
        allowed = {
            "index.html", "control.html", "settings.html", "styles.css", "dashboard.css", "ai-detail.css", "zone-detail.css", "history.css", "history-h21.css", "history-h22.css", "history-h4.css", "history-h41-alerts.css", "history-h42-alert-folders.css", "history-h43-alert-pagination.css", "service-dashboard.css", "sidebar.css", "v2-weather.css",
            "cm5-watchdog.css", "schedule.css", "zigbee-settings.css", "zigbee-stage13.css",
            "dashboard.js", "dashboard-live.js", "ai-operator-view.js", "zone-detail.js", "history.js", "history-h21.js", "history-h22.js", "history-h23.js", "history-h3.js", "history-h4.js", "history-h4-storage.js", "history-h41-alerts.js", "history-h42-alert-folders.js", "history-h43-alert-pagination.js", "service-dashboard.js", "cm5-watchdog.js", "app.js", "tacho.js", "alerts.js", "schedule.js", "zigbee-settings.js",
        }
        if relative not in allowed:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        candidate = (self.server.static_root / relative).resolve()
        if candidate.parent != self.server.static_root or not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = candidate.read_bytes()

        # The dashboard already loads the Stage 2 AI assets. Keep staged presentation
        # modules in separate source files, but append them to the existing dashboard
        # asset responses so the shell stays stable while GUI work is validated.
        if relative == "ai-operator-view.js":
            for name in ("zone-detail.js", "history.js"):
                module = (self.server.static_root / name).resolve()
                if module.parent == self.server.static_root and module.is_file():
                    content += b"\n\n" + module.read_bytes()
            h21_js = (self.server.static_root / "history-h21.js").resolve()
            if h21_js.parent == self.server.static_root and h21_js.is_file():
                content += b"\n\n" + h21_js.read_bytes()
            h22_js = (self.server.static_root / "history-h22.js").resolve()
            if h22_js.parent == self.server.static_root and h22_js.is_file():
                content += b"\n\n" + h22_js.read_bytes()
            h23_js = (self.server.static_root / "history-h23.js").resolve()
            if h23_js.parent == self.server.static_root and h23_js.is_file():
                content += b"\n\n" + h23_js.read_bytes()
            h3_js = (self.server.static_root / "history-h3.js").resolve()
            if h3_js.parent == self.server.static_root and h3_js.is_file():
                content += b"\n\n" + h3_js.read_bytes()
            h4_js = (self.server.static_root / "history-h4.js").resolve()
            if h4_js.parent == self.server.static_root and h4_js.is_file():
                content += b"\n\n" + h4_js.read_bytes()
            h4_storage_js = (self.server.static_root / "history-h4-storage.js").resolve()
            if h4_storage_js.parent == self.server.static_root and h4_storage_js.is_file():
                content += b"\n\n" + h4_storage_js.read_bytes()
            h41_alert_js = (self.server.static_root / "history-h41-alerts.js").resolve()
            if h41_alert_js.parent == self.server.static_root and h41_alert_js.is_file():
                content += b"\n\n" + h41_alert_js.read_bytes()
            h42_alert_js = (self.server.static_root / "history-h42-alert-folders.js").resolve()
            if h42_alert_js.parent == self.server.static_root and h42_alert_js.is_file():
                content += b"\n\n" + h42_alert_js.read_bytes()
            h43_alert_js = (self.server.static_root / "history-h43-alert-pagination.js").resolve()
            if h43_alert_js.parent == self.server.static_root and h43_alert_js.is_file():
                content += b"\n\n" + h43_alert_js.read_bytes()
            service_js = (self.server.static_root / "service-dashboard.js").resolve()
            if service_js.parent == self.server.static_root and service_js.is_file():
                content += b"\n\n" + service_js.read_bytes()
        elif relative == "ai-detail.css":
            for name in ("zone-detail.css", "history.css"):
                module = (self.server.static_root / name).resolve()
                if module.parent == self.server.static_root and module.is_file():
                    content += b"\n\n" + module.read_bytes()
            h21_css = (self.server.static_root / "history-h21.css").resolve()
            if h21_css.parent == self.server.static_root and h21_css.is_file():
                content += b"\n\n" + h21_css.read_bytes()
            h22_css = (self.server.static_root / "history-h22.css").resolve()
            if h22_css.parent == self.server.static_root and h22_css.is_file():
                content += b"\n\n" + h22_css.read_bytes()
            h4_css = (self.server.static_root / "history-h4.css").resolve()
            if h4_css.parent == self.server.static_root and h4_css.is_file():
                content += b"\n\n" + h4_css.read_bytes()
            h41_alert_css = (self.server.static_root / "history-h41-alerts.css").resolve()
            if h41_alert_css.parent == self.server.static_root and h41_alert_css.is_file():
                content += b"\n\n" + h41_alert_css.read_bytes()
            h42_alert_css = (self.server.static_root / "history-h42-alert-folders.css").resolve()
            if h42_alert_css.parent == self.server.static_root and h42_alert_css.is_file():
                content += b"\n\n" + h42_alert_css.read_bytes()
            h43_alert_css = (self.server.static_root / "history-h43-alert-pagination.css").resolve()
            if h43_alert_css.parent == self.server.static_root and h43_alert_css.is_file():
                content += b"\n\n" + h43_alert_css.read_bytes()
            service_css = (self.server.static_root / "service-dashboard.css").resolve()
            if service_css.parent == self.server.static_root and service_css.is_file():
                content += b"\n\n" + service_css.read_bytes()

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