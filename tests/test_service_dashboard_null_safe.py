from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class ServiceDashboardNullSafeTest(unittest.TestCase):
    def test_nullable_backend_objects_use_explicit_null_safe_projection(self) -> None:
        js = (STATIC / "service-dashboard.js").read_text(encoding="utf-8")

        self.assertIn("function objectOrEmpty(value)", js)
        self.assertIn(
            'return value !== null && typeof value === "object" && !Array.isArray(value) ? value : {};',
            js,
        )

        required = (
            "const memory = objectOrEmpty(system && system.memory);",
            "const storage = objectOrEmpty(system && system.root_storage);",
            "const load = objectOrEmpty(system && system.load_average);",
            "const power = objectOrEmpty(system && system.power);",
            "const setpoints = objectOrEmpty(core && core.setpoints);",
            "const v2 = objectOrEmpty(core && core.alert_v2);",
            "const sensor = objectOrEmpty(hardware && hardware.sensor_bus);",
            "const aero = objectOrEmpty(hardware && hardware.aero);",
            "const tacho = objectOrEmpty(hardware && hardware.tacho);",
            "const zigbee = objectOrEmpty(hardware && hardware.zigbee);",
            "const route = objectOrEmpty(network && network.default_route);",
            "const ai = objectOrEmpty(network && network.ai_server);",
            "const mqtt = objectOrEmpty(network && network.mqtt);",
            "const plane = objectOrEmpty(network && network.service_plane);",
            "const planeNetwork = objectOrEmpty(plane.network);",
            "const telemetry = objectOrEmpty(data && data.telemetry);",
            "const alerts = objectOrEmpty(data && data.alerts);",
            "const rollups = objectOrEmpty(telemetry.rollups);",
            "const agent = objectOrEmpty(plane.agent);",
        )
        for line in required:
            self.assertIn(line, js)

    def test_null_service_payload_is_rejected_before_renderer(self) -> None:
        js = (STATIC / "service-dashboard.js").read_text(encoding="utf-8")
        self.assertIn(
            '!response.ok || payload.ok !== true || !payload.service || typeof payload.service !== "object"',
            js,
        )

    def test_previous_typeof_null_traps_are_not_used_for_network_fields(self) -> None:
        js = (STATIC / "service-dashboard.js").read_text(encoding="utf-8")
        self.assertNotIn(
            'typeof network.default_route === "object" ? network.default_route : {}',
            js,
        )
        self.assertNotIn(
            'typeof plane.network === "object" ? plane.network : {}',
            js,
        )


if __name__ == "__main__":
    unittest.main()
