from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from threading import Thread
import unittest
from urllib import parse

from ventilation_core.advisory.client import AIBridgeAdvisoryClient


SOURCE_ID = "workshop-ventilation-cm5-01"


def advisory_payload() -> dict:
    return {
        "delivery_schema_version": 1,
        "analysis_id": "5cf9d21e-e2d2-4b0c-920e-c4a67aef135a",
        "source_id": SOURCE_ID,
        "window_start": "2026-08-10T15:15:00Z",
        "window_end": "2026-08-10T15:30:00Z",
        "created_at": "2026-08-10T15:37:36Z",
        "sample_count": 180,
        "model": "qwen3.6:35b",
        "prompt_version": "ventilation-v10-baseline-safe",
        "advisory_only": True,
        "experimental": True,
        "control_actions_supported": False,
        "result": {
            "schema_version": 2,
            "status": "no_anomaly_detected",
            "analysis_pl": "Raport testowy.",
            "operator_recommendation_pl": "Treść wyłącznie doradcza.",
            "data_quality_pl": "Kompletne okno.",
        },
    }


class AdvisoryClientTest(unittest.TestCase):
    def test_fetch_latest_uses_get_and_validates_read_only_contract(self) -> None:
        observed = {}
        payload = advisory_payload()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                split = parse.urlsplit(self.path)
                observed["path"] = split.path
                observed["query"] = parse.parse_qs(split.query)
                body = json.dumps(payload).encode("utf-8")
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
        result = AIBridgeAdvisoryClient(f"http://{host}:{port}").fetch_latest(SOURCE_ID)
        thread.join(timeout=2)
        httpd.server_close()

        self.assertEqual(observed["path"], "/api/v1/ventilation/analysis/latest")
        self.assertEqual(observed["query"], {"source_id": [SOURCE_ID]})
        self.assertEqual(result, payload)
        self.assertTrue(result["advisory_only"])
        self.assertTrue(result["experimental"])
        self.assertFalse(result["control_actions_supported"])

    def test_fetch_latest_treats_404_as_no_analysis_yet(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def log_message(self, format, *args):
                return

        httpd = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=httpd.handle_request)
        thread.start()
        host, port = httpd.server_address
        result = AIBridgeAdvisoryClient(f"http://{host}:{port}").fetch_latest(SOURCE_ID)
        thread.join(timeout=2)
        httpd.server_close()
        self.assertIsNone(result)

    def test_client_rejects_payload_that_claims_control_support(self) -> None:
        payload = advisory_payload()
        payload["control_actions_supported"] = True

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(payload).encode("utf-8")
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
        with self.assertRaisesRegex(RuntimeError, "control_actions_supported=false"):
            AIBridgeAdvisoryClient(f"http://{host}:{port}").fetch_latest(SOURCE_ID)
        thread.join(timeout=2)
        httpd.server_close()


if __name__ == "__main__":
    unittest.main()
