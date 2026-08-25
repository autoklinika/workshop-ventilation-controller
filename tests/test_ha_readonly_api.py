import http.client
import json
import threading
import unittest

from ventilation_core.ha_api.app import HaReadOnlyApplication
from ventilation_core.ha_api.client import CoreReadOnlyGateway
from ventilation_core.ha_api.server import HaApiHttpServer
from ventilation_core.web.client import CoreClientError


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        if not self.responses:
            raise AssertionError("unexpected core request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeReadOnlyCore:
    def __init__(self):
        self.status_response = {"ok": True, "state": {"mode": "STOP", "alert_v2": {"active_weight": 0}}}
        self.alerts_response = {"ok": True, "active": [], "history": []}
        self.status_error = None
        self.status_calls = 0
        self.alert_limits = []

    def status(self):
        self.status_calls += 1
        if self.status_error is not None:
            raise self.status_error
        return self.status_response

    def alerts(self, limit=200):
        self.alert_limits.append(limit)
        return self.alerts_response


class CoreReadOnlyGatewayTest(unittest.TestCase):
    def test_gateway_exposes_only_allowlisted_read_commands(self):
        transport = FakeTransport(
            [
                {"ok": True, "state": {"mode": "STOP"}},
                {"ok": True, "active": [], "history": []},
            ]
        )
        gateway = CoreReadOnlyGateway(transport)

        self.assertEqual(gateway.status()["state"]["mode"], "STOP")
        self.assertEqual(gateway.alerts(), {"ok": True, "active": [], "history": []})
        self.assertEqual(
            transport.requests,
            [
                {"command": "status"},
                {"command": "alerts", "limit": 200},
            ],
        )
        self.assertFalse(hasattr(gateway, "request"))

    def test_gateway_rejects_invalid_alert_limit_without_core_request(self):
        transport = FakeTransport([])
        gateway = CoreReadOnlyGateway(transport)
        for invalid in (0, 1001, True, 2.5, "200", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    gateway.alerts(invalid)
        self.assertEqual(transport.requests, [])


class HaReadOnlyApplicationTest(unittest.TestCase):
    def test_state_and_alerts_are_read_only_views(self):
        core = FakeReadOnlyCore()
        app = HaReadOnlyApplication(core)

        state = app.handle("GET", "/api/ha/v1/state")
        alerts = app.handle("GET", "/api/ha/v1/alerts")

        self.assertEqual(state.status, 200)
        self.assertEqual(state.payload, core.status_response)
        self.assertEqual(alerts.status, 200)
        self.assertEqual(alerts.payload, core.alerts_response)
        self.assertEqual(core.status_calls, 1)
        self.assertEqual(core.alert_limits, [200])

    def test_every_non_get_method_is_rejected_before_touching_core(self):
        core = FakeReadOnlyCore()
        app = HaReadOnlyApplication(core)

        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE"):
            with self.subTest(method=method):
                response = app.handle(method, "/api/ha/v1/state")
                self.assertEqual(response.status, 405)
                self.assertFalse(response.payload["ok"])

        self.assertEqual(core.status_calls, 0)
        self.assertEqual(core.alert_limits, [])

    def test_unknown_get_route_is_not_forwarded_to_core(self):
        core = FakeReadOnlyCore()
        response = HaReadOnlyApplication(core).handle("GET", "/api/ha/v1/manual/fans")
        self.assertEqual(response.status, 404)
        self.assertEqual(core.status_calls, 0)
        self.assertEqual(core.alert_limits, [])

    def test_health_reports_api_up_when_core_is_unavailable(self):
        core = FakeReadOnlyCore()
        core.status_error = CoreClientError("socket unavailable")
        response = HaReadOnlyApplication(core).handle("GET", "/api/ha/v1/health")
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["read_only"])
        self.assertFalse(response.payload["core_available"])


class HaApiHttpServerTest(unittest.TestCase):
    def setUp(self):
        self.core = FakeReadOnlyCore()
        self.server = HaApiHttpServer(("127.0.0.1", 0), HaReadOnlyApplication(self.core))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=2)
        try:
            payload = None if body is None else json.dumps(body)
            headers = {} if payload is None else {"Content-Type": "application/json"}
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            data = json.loads(response.read().decode("utf-8"))
            return response.status, dict(response.getheaders()), data
        finally:
            connection.close()

    def test_http_get_state_works_and_declares_get_only(self):
        status, headers, payload = self.request("GET", "/api/ha/v1/state")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Allow"], "GET")
        self.assertEqual(payload, self.core.status_response)

    def test_http_write_methods_are_rejected_without_core_side_effect(self):
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                status, headers, payload = self.request(
                    method,
                    "/api/ha/v1/state",
                    {"command": "stop", "supply_voltage": 10.0},
                )
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "GET")
                self.assertFalse(payload["ok"])

        self.assertEqual(self.core.status_calls, 0)
        self.assertEqual(self.core.alert_limits, [])


if __name__ == "__main__":
    unittest.main()
