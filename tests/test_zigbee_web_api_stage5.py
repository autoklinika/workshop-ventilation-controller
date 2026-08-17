import unittest

from ventilation_core.web.app import WebApplication


class FakeCoreClient:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return self.response


class ZigbeeWebApiStage5Tests(unittest.TestCase):
    def test_dedicated_zigbee_endpoint_projects_authoritative_core_state(self):
        zigbee = {
            "broker_host": "127.0.0.1",
            "broker_port": 1883,
            "base_topic": "zigbee2mqtt",
            "running": True,
            "connected": True,
            "devices": [
                {
                    "role": "supply",
                    "friendly_name": "temp_nawiew",
                    "ieee_address": "0xa4c13810e66fffff",
                    "temperature_celsius": 28.6,
                    "battery_percent": 100.0,
                    "linkquality": 76,
                    "messages": 2,
                    "parse_errors": 0,
                },
                {
                    "role": "extract",
                    "friendly_name": "temp_wywiew",
                    "ieee_address": "0xa4c13810bdedffff",
                    "temperature_celsius": 27.8,
                    "battery_percent": 100.0,
                    "linkquality": 36,
                    "messages": 1,
                    "parse_errors": 0,
                },
            ],
        }
        core = FakeCoreClient({"ok": True, "state": {"mode": "FAULT", "zigbee": zigbee}})

        response = WebApplication(core).handle("GET", "/api/v1/zigbee")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload, {"ok": True, "zigbee": zigbee})
        self.assertEqual(core.requests, [{"command": "status"}])

    def test_endpoint_reports_unavailable_when_core_has_no_zigbee_state(self):
        core = FakeCoreClient({"ok": True, "state": {"mode": "STOP", "zigbee": None}})

        response = WebApplication(core).handle("GET", "/api/v1/zigbee")

        self.assertEqual(response.status, 503)
        self.assertFalse(response.payload["ok"])
        self.assertIn("not available", response.payload["error"])
        self.assertEqual(core.requests, [{"command": "status"}])

    def test_endpoint_does_not_expose_zigbee_write_or_generic_proxy(self):
        core = FakeCoreClient({"ok": True, "state": {"zigbee": {}}})
        app = WebApplication(core)

        self.assertEqual(app.handle("POST", "/api/v1/zigbee", {}).status, 404)
        self.assertEqual(app.handle("POST", "/api/v1/zigbee/permit-join", {}).status, 404)
        self.assertEqual(core.requests, [])


if __name__ == "__main__":
    unittest.main()
