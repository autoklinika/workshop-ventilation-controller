import unittest

from ventilation_core.ha_api.app import HaReadOnlyApplication


class FakeReadOnlyCore:
    def __init__(self, state):
        self.state = state
        self.status_calls = 0
        self.alert_calls = 0

    def status(self):
        self.status_calls += 1
        return {"ok": True, "state": self.state}

    def alerts(self, limit=200):
        self.alert_calls += 1
        return {"ok": True, "active": [], "history": []}


class HaSnapshotTest(unittest.TestCase):
    def test_snapshot_is_stable_read_only_projection_of_core_status(self):
        state = {
            "mode": "STOP",
            "hardware_ready": True,
            "output_state_known": True,
            "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
            "sensor_bus": {
                "ready": True,
                "worker_alive": True,
                "last_error": None,
                "nodes": [
                    {
                        "slave_address": 1,
                        "online": True,
                        "usable": True,
                        "measurement_valid": True,
                        "measurement_stale": False,
                        "reading": {
                            "temperature_celsius": 25.32,
                            "humidity_percent": 41.47,
                            "pm1_0_ug_m3": 3.9,
                            "pm2_5_ug_m3": 4.2,
                            "pm4_0_ug_m3": 4.3,
                            "pm10_0_ug_m3": 4.3,
                            "voc_index": 368.0,
                            "nox_index": 1.0,
                        },
                    },
                    {
                        "slave_address": 2,
                        "online": True,
                        "usable": True,
                        "measurement_valid": True,
                        "measurement_stale": False,
                        "reading": {"temperature_celsius": 24.89, "humidity_percent": 43.34},
                    },
                ],
            },
            "tacho": {
                "supply": {"rpm": 0.0, "valid": False, "frequency_hz": 0.0},
                "extract": {"rpm": 0.0, "valid": False, "frequency_hz": 0.0},
            },
            "aero_bus": {
                "online": False,
                "usable": False,
                "last_error": "No response or incomplete Modbus header",
                "telemetry": {"humidity_percent": None},
            },
            "zigbee": {
                "running": True,
                "connected": True,
                "bridge_online": None,
                "last_error": None,
            },
            "active_alarms": [
                {
                    "alert_id": 369,
                    "code": "AERO_BUS_UNAVAILABLE",
                    "source": "aero_bus",
                    "severity": "warning",
                    "message": "Rekuperator AERO: brak poprawnej komunikacji",
                    "active_since": "2026-08-25T16:13:48+00:00",
                    "acknowledged": False,
                    "alert_v2": {
                        "weight": 4,
                        "severity": "critical",
                        "title": "Rekuperator AERO niedostępny",
                        "hmi_color": "red",
                        "affects_control": True,
                    },
                }
            ],
            "alert_v2": {
                "policy_version": "2026-08-21.2",
                "active_weight": 4,
                "hmi_color": "red",
                "control_policy_applied": False,
            },
        }
        core = FakeReadOnlyCore(state)
        response = HaReadOnlyApplication(core).handle("GET", "/api/ha/v1/snapshot")

        self.assertEqual(response.status, 200)
        snapshot = response.payload
        self.assertTrue(snapshot["ok"])
        self.assertTrue(snapshot["read_only"])
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["mode"], "STOP")
        self.assertEqual(snapshot["sensor_bus"]["nodes"]["1"]["temperature_celsius"], 25.32)
        self.assertEqual(snapshot["sensor_bus"]["nodes"]["1"]["voc_index"], 368.0)
        self.assertFalse(snapshot["aero"]["online"])
        self.assertEqual(snapshot["alerts"]["active_count"], 1)
        self.assertEqual(snapshot["alerts"]["active_ids"], [369])
        self.assertEqual(snapshot["alerts"]["active_weight"], 4)
        self.assertFalse(snapshot["alerts"]["control_policy_applied"])
        self.assertEqual(snapshot["alerts"]["active"][0]["severity"], "critical")
        self.assertEqual(snapshot["alerts"]["active"][0]["code"], "AERO_BUS_UNAVAILABLE")

        self.assertEqual(core.status_calls, 1)
        self.assertEqual(core.alert_calls, 0)

    def test_snapshot_tolerates_optional_subsystems_missing(self):
        core = FakeReadOnlyCore(
            {
                "mode": "STOP",
                "hardware_ready": True,
                "output_state_known": True,
                "active_alarms": [],
            }
        )
        response = HaReadOnlyApplication(core).handle("GET", "/api/ha/v1/snapshot")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["sensor_bus"]["nodes"], {})
        self.assertIsNone(response.payload["fans"]["supply"]["rpm"])
        self.assertEqual(response.payload["alerts"]["active_count"], 0)
        self.assertEqual(response.payload["alerts"]["active_ids"], [])
        self.assertEqual(core.status_calls, 1)
        self.assertEqual(core.alert_calls, 0)

    def test_snapshot_write_attempt_is_rejected_before_core_access(self):
        core = FakeReadOnlyCore({"mode": "STOP"})
        response = HaReadOnlyApplication(core).handle("POST", "/api/ha/v1/snapshot")
        self.assertEqual(response.status, 405)
        self.assertEqual(core.status_calls, 0)
        self.assertEqual(core.alert_calls, 0)


if __name__ == "__main__":
    unittest.main()
