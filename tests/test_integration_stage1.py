from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import unittest

from ventilation_core.application.shadow_service import ShadowAlertingVentilationService
from ventilation_core.application.zigbee_service import ZigbeeAlertingVentilationService
from ventilation_core.domain.models import AlarmCode, CoreState


ROOT = Path(__file__).resolve().parents[1]


class IntegrationStage1ContractTests(unittest.TestCase):
    def test_shadow_composes_on_top_of_zigbee_alerting_service(self) -> None:
        self.assertTrue(
            issubclass(ShadowAlertingVentilationService, ZigbeeAlertingVentilationService)
        )

    def test_core_state_contains_all_integrated_projections(self) -> None:
        names = {field.name for field in fields(CoreState)}
        self.assertTrue({"zigbee", "schedule", "shadow_automation"}.issubset(names))
        self.assertEqual(AlarmCode.ZIGBEE_LOW_BATTERY.value, "ZIGBEE_LOW_BATTERY")

    def test_runtime_exposes_schedule_and_zigbee_commands(self) -> None:
        source = (ROOT / "src/ventilation_core/runtime/server.py").read_text(encoding="utf-8")
        for token in (
            'command == "schedule"',
            'command == "schedule-replace"',
            'command == "zigbee-permit-join"',
            'command == "zigbee-request-remove-device"',
            'command == "zigbee-assign-role"',
        ):
            self.assertIn(token, source)

    def test_web_boundary_exposes_history_schedule_and_zigbee(self) -> None:
        source = (ROOT / "src/ventilation_core/web/app.py").read_text(encoding="utf-8")
        for token in (
            'path == "/api/v1/history/status"',
            'path == "/api/v1/history/query"',
            'path == "/api/v1/schedule"',
            'path == "/api/v1/schedule/zone"',
            'path == "/api/v1/zigbee"',
            'path == "/api/v1/zigbee/role"',
        ):
            self.assertIn(token, source)

    def test_settings_page_contains_both_editors(self) -> None:
        html = (ROOT / "src/ventilation_core/web/static/settings.html").read_text(encoding="utf-8")
        self.assertIn('id="zigbeeSettingsMount"', html)
        self.assertIn('src="/zigbee-settings.js"', html)
        self.assertIn('data-zone-editor="zone-1"', html)
        self.assertIn('data-zone-editor="zone-2"', html)
        self.assertIn('src="/schedule.js"', html)

    def test_systemd_starts_schedule_and_zigbee_boundaries_together(self) -> None:
        unit = (ROOT / "deploy/systemd/ventilation-core.service").read_text(encoding="utf-8")
        self.assertIn("--automation-db /var/lib/workshop-ventilation/automation.sqlite3", unit)
        self.assertIn("--zigbee-mqtt-host 127.0.0.1", unit)
        self.assertIn("--zigbee-roles-file /var/lib/workshop-ventilation/zigbee-roles.json", unit)
        self.assertIn("Wants=mosquitto.service zigbee2mqtt.service", unit)


if __name__ == "__main__":
    unittest.main()
