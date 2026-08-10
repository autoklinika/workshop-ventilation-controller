from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import socket
import tempfile
from threading import Thread
import unittest

from ventilation_core.telemetry.core_client import CoreStateClient
from ventilation_core.telemetry.http_client import AIBridgeTelemetryClient


class TelemetryClientsTest(unittest.TestCase):
    def test_core_state_client_uses_read_only_status_command(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        socket_path = Path(tempdir.name) / "core.sock"
        received = {}
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        server.listen(1)

        def serve() -> None:
            conn, _ = server.accept()
            with conn:
                raw = b""
                while not raw.endswith(b"\n"):
                    raw += conn.recv(4096)
                received.update(json.loads(raw.decode("utf-8")))
                conn.sendall((json.dumps({"ok": True, "state": {"mode": "STOP"}}) + "\n").encode("utf-8"))
            server.close()

        thread = Thread(target=serve)
        thread.start()
        state = CoreStateClient(socket_path).read_state()
        thread.join(timeout=2)
        self.assertEqual(received, {"command": "status"})
        self.assertEqual(state, {"mode": "STOP"})

    def test_ai_bridge_client_posts_expected_endpoint(self) -> None:
        observed = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                observed["path"] = self.path
                length = int(self.headers["Content-Length"])
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                observed["payload"] = payload
                sample_count = len(payload["samples"])
                ack = {
                    "schema_version": 1,
                    "source_id": payload["source_id"],
                    "batch_id": payload["batch_id"],
                    "status": "accepted",
                    "received": sample_count,
                    "stored": sample_count,
                    "duplicates": 0,
                    "rejected": 0,
                    "server_time": "2026-08-10T09:00:00Z",
                }
                body = json.dumps(ack).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        httpd = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=httpd.handle_request)
        thread.start()
        host, port = httpd.server_address
        payload = {
            "schema_version": 1,
            "source_id": "workshop-ventilation-cm5-01",
            "batch_id": "batch-1",
            "created_at": "2026-08-10T09:00:00+00:00",
            "samples": [{"sample_id": "sample-1"}],
        }
        ack = AIBridgeTelemetryClient(f"http://{host}:{port}").send_batch(payload)
        thread.join(timeout=2)
        httpd.server_close()
        self.assertEqual(observed["path"], "/api/v1/ventilation/telemetry/batches")
        self.assertEqual(observed["payload"], payload)
        self.assertEqual(ack["stored"], 1)


if __name__ == "__main__":
    unittest.main()
