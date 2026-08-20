from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from ventilation_core.web.service_status_contract import NullSafeServiceStatusProvider


ROOT = Path(__file__).resolve().parents[1]


class FakeProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get_snapshot(self):
        return self.snapshot


class ServiceDashboardNullGuardTest(unittest.TestCase):
    def test_nullable_service_sections_are_normalized_without_mutating_source(self) -> None:
        source = {
            "available": True,
            "configured": True,
            "read_only": True,
            "summary": [None, {"label": "SYSTEM", "state": "ok"}],
            "services": [None, {"unit": "ventilation-core.service"}],
            "system": {
                "memory": None,
                "root_storage": None,
                "load_average": None,
                "power": None,
            },
            "core": None,
            "hardware": {
                "sensor_bus": None,
                "aero": None,
                "tacho": {
                    "supply": None,
                    "extract": {
                        "service_status": None,
                    },
                },
                "zigbee": None,
                "sen55_nodes": [None, {"slave_address": 1}],
            },
            "network": {
                "default_route": None,
                "ai_server": None,
                "mqtt": None,
                "service_plane": {
                    "agent": None,
                    "network": None,
                    "nodes": [None, {"node_id": "sensor-node-1"}],
                },
                "interfaces": [None, {"name": "eth0"}],
            },
            "data": {
                "telemetry": None,
                "alerts": None,
            },
            "ai": None,
        }
        original = deepcopy(source)

        snapshot = NullSafeServiceStatusProvider(FakeProvider(source)).get_snapshot()

        self.assertEqual(source, original)
        self.assertEqual(snapshot["network"]["default_route"], {})
        self.assertEqual(snapshot["network"]["service_plane"]["network"], {})
        self.assertEqual(snapshot["network"]["service_plane"]["agent"], {})
        self.assertEqual(snapshot["core"]["setpoints"], {})
        self.assertEqual(snapshot["core"]["alert_v2"], {})
        self.assertEqual(snapshot["system"]["memory"], {})
        self.assertEqual(snapshot["hardware"]["sensor_bus"], {})
        self.assertEqual(snapshot["hardware"]["tacho"]["supply"], {"service_status": {}})
        self.assertEqual(
            snapshot["hardware"]["tacho"]["extract"],
            {"service_status": {}},
        )
        self.assertEqual(snapshot["data"]["telemetry"]["rollups"], {})
        self.assertEqual(snapshot["summary"], [{"label": "SYSTEM", "state": "ok"}])
        self.assertEqual(snapshot["services"], [{"unit": "ventilation-core.service"}])
        self.assertEqual(snapshot["hardware"]["sen55_nodes"], [{"slave_address": 1}])
        self.assertEqual(snapshot["network"]["interfaces"], [{"name": "eth0"}])
        self.assertEqual(
            snapshot["network"]["service_plane"]["nodes"],
            [{"node_id": "sensor-node-1"}],
        )

    def test_invalid_root_snapshot_degrades_to_read_only_unavailable_contract(self) -> None:
        snapshot = NullSafeServiceStatusProvider(FakeProvider(None)).get_snapshot()

        self.assertFalse(snapshot["available"])
        self.assertTrue(snapshot["configured"])
        self.assertTrue(snapshot["read_only"])
        self.assertEqual(snapshot["summary"], [])
        self.assertEqual(snapshot["services"], [])
        self.assertIn("invalid SERVICE diagnostic snapshot", snapshot["error"])

    def test_web_main_applies_null_safe_adapter_to_real_service_provider(self) -> None:
        main = (ROOT / "src" / "ventilation_core" / "web" / "main.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("ServiceStatusProvider", main)
        self.assertIn("NullSafeServiceStatusProvider", main)
        self.assertIn("raw_service_status = ServiceStatusProvider(", main)
        self.assertIn(
            "service_status = NullSafeServiceStatusProvider(raw_service_status)",
            main,
        )


if __name__ == "__main__":
    unittest.main()
