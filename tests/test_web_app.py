import unittest

from ventilation_core.web.app import WebApplication
from ventilation_core.web.client import CoreClientError
from ventilation_core.web.config import WebUiConfig


class FakeCoreClient:
    def __init__(self, response=None, error=None):
        self.response = response or {"ok": True, "state": {"mode": "STOP"}}
        self.error = error
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        if self.error is not None:
            raise self.error
        return self.response


class WebApplicationTest(unittest.TestCase):
    def test_public_config_exposes_display_mapping_but_no_control_capability(self):
        core = FakeCoreClient()
        config = WebUiConfig(zone1_name="Strefa testowa A", zone1_sensor_address=2, zone2_name="Strefa testowa B", zone2_sensor_address=1)
        response = WebApplication(core, config).handle("GET", "/api/v1/config")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["config"]["zone1"]["sensor_address"], 2)
        self.assertFalse(response.payload["config"]["automation_enabled"])
        self.assertFalse(response.payload["config"]["ai_control_enabled"])
        self.assertEqual(core.requests, [])

    def test_state_uses_authoritative_core_status(self):
        core = FakeCoreClient({"ok": True, "state": {"mode": "STOP"}})
        response = WebApplication(core).handle("GET", "/api/v1/state")
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests, [{"command": "status"}])

    def test_alerts_are_read_from_authoritative_core_registry(self):
        payload = {
            "ok": True,
            "active": [{"alert_id": 7, "active": True}],
            "history": [{"alert_id": 7, "active": True}],
        }
        core = FakeCoreClient(payload)
        response = WebApplication(core).handle("GET", "/api/v1/alerts")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload, payload)
        self.assertEqual(core.requests, [{"command": "alerts", "limit": 200}])

    def test_alert_ack_forwards_only_positive_alert_id_to_core(self):
        core = FakeCoreClient({"ok": True, "alert": {"alert_id": 7, "acknowledged": True}})
        response = WebApplication(core).handle("POST", "/api/v1/alerts/ack", {"alert_id": 7})
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests, [{"command": "ack-alert", "alert_id": 7}])

        for invalid in (0, -1, True, 2.5, "7", None):
            with self.subTest(invalid=invalid):
                bad_core = FakeCoreClient()
                bad_response = WebApplication(bad_core).handle("POST", "/api/v1/alerts/ack", {"alert_id": invalid})
                self.assertEqual(bad_response.status, 400)
                self.assertEqual(bad_core.requests, [])

    def test_manual_fans_maps_only_to_guarded_set_command(self):
        core = FakeCoreClient({"ok": True, "state": {"mode": "MANUAL"}})
        response = WebApplication(core).handle("POST", "/api/v1/manual/fans", {"supply_voltage": 3.0, "extract_voltage": 4.5})
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests, [{"command": "set", "supply_voltage": 3.0, "extract_voltage": 4.5}])

    def test_manual_fan_voltage_rejects_dead_band_and_out_of_range(self):
        for value in (-1, 0.5, 10.5, float("inf")):
            with self.subTest(value=value):
                core = FakeCoreClient()
                response = WebApplication(core).handle("POST", "/api/v1/manual/fans", {"supply_voltage": value, "extract_voltage": 0.0})
                self.assertEqual(response.status, 400)
                self.assertEqual(core.requests, [])

    def test_stop_maps_to_stop_and_does_not_expose_shutdown(self):
        core = FakeCoreClient({"ok": True, "state": {"mode": "STOP"}})
        app = WebApplication(core)
        self.assertEqual(app.handle("POST", "/api/v1/manual/stop", {}).status, 200)
        self.assertEqual(core.requests, [{"command": "stop"}])
        self.assertEqual(app.handle("POST", "/api/v1/shutdown", {}).status, 404)
        self.assertEqual(core.requests, [{"command": "stop"}])

    def test_aero_speed_accepts_only_0_to_3(self):
        for speed in (0, 1, 2, 3):
            with self.subTest(speed=speed):
                core = FakeCoreClient({"ok": True, "aero_control": {"state": "succeeded"}})
                response = WebApplication(core).handle("POST", "/api/v1/manual/aero/speed", {"speed": speed})
                self.assertEqual(response.status, 200)
                self.assertEqual(core.requests, [{"command": "aero-speed", "speed": speed}])
        for speed in (-1, 4, True, 2.0, "2"):
            with self.subTest(speed=speed):
                core = FakeCoreClient()
                response = WebApplication(core).handle("POST", "/api/v1/manual/aero/speed", {"speed": speed})
                self.assertEqual(response.status, 400)
                self.assertEqual(core.requests, [])

    def test_aero_airing_requires_boolean(self):
        core = FakeCoreClient({"ok": True, "aero_control": {"state": "succeeded"}})
        response = WebApplication(core).handle("POST", "/api/v1/manual/aero/airing", {"enabled": True})
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests, [{"command": "aero-airing", "enabled": True}])
        bad_core = FakeCoreClient()
        self.assertEqual(WebApplication(bad_core).handle("POST", "/api/v1/manual/aero/airing", {"enabled": 1}).status, 400)
        self.assertEqual(bad_core.requests, [])

    def test_core_rejection_is_not_reported_as_success(self):
        core = FakeCoreClient({"ok": False, "error": "AERO BUS is not ready for control"})
        response = WebApplication(core).handle("POST", "/api/v1/manual/aero/speed", {"speed": 2})
        self.assertEqual(response.status, 409)
        self.assertFalse(response.payload["ok"])

    def test_core_transport_failure_becomes_service_unavailable(self):
        core = FakeCoreClient(error=CoreClientError("socket unavailable"))
        response = WebApplication(core).handle("GET", "/api/v1/state")
        self.assertEqual(response.status, 503)

    def test_health_stays_up_when_core_is_down(self):
        core = FakeCoreClient(error=CoreClientError("socket unavailable"))
        response = WebApplication(core).handle("GET", "/api/v1/health")
        self.assertEqual(response.status, 200)
        self.assertFalse(response.payload["core_available"])

    def test_no_generic_command_proxy_exists(self):
        core = FakeCoreClient()
        response = WebApplication(core).handle("POST", "/api/v1/command", {"command": "shutdown"})
        self.assertEqual(response.status, 404)
        self.assertEqual(core.requests, [])


if __name__ == "__main__":
    unittest.main()
