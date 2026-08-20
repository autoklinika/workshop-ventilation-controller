from __future__ import annotations

from pathlib import Path
import unittest

from ventilation_core.web.service_status import ServiceStatusProvider


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class ServiceDashboardPolishTest(unittest.TestCase):
    def test_tacho_stop_semantics_are_owned_by_backend(self) -> None:
        self.assertEqual(
            ServiceStatusProvider._tacho_service_status("STOP", {"valid": False}),
            {"state": "idle", "text": "N/D — STOP"},
        )
        self.assertEqual(
            ServiceStatusProvider._tacho_service_status("MANUAL", {"valid": False}),
            {"state": "warning", "text": "NIE"},
        )
        self.assertEqual(
            ServiceStatusProvider._tacho_service_status("MANUAL", {"valid": True}),
            {"state": "ok", "text": "TAK"},
        )
        self.assertEqual(
            ServiceStatusProvider._tacho_service_status("STOP", None),
            {"state": "unavailable", "text": "BRAK DANYCH"},
        )

    def test_browser_consumes_backend_tacho_status_without_classifying_valid(self) -> None:
        js = (STATIC / "service-dashboard.js").read_text(encoding="utf-8")
        self.assertIn("supply.service_status", js)
        self.assertIn("extract.service_status", js)
        self.assertIn("semanticClass(supplyStatus.state)", js)
        self.assertIn("semanticClass(extractStatus.state)", js)
        self.assertNotIn("formatBool(supply.valid)", js)
        self.assertNotIn("formatBool(extract.valid)", js)
        self.assertNotIn("boolClass(supply.valid)", js)
        self.assertNotIn("boolClass(extract.valid)", js)

    def test_historical_power_flags_are_presented_as_warning_not_active_fault(self) -> None:
        js = (STATIC / "service-dashboard.js").read_text(encoding="utf-8")
        self.assertIn(
            'power.undervoltage_occurred === true ? "v2-service-warn"',
            js,
        )
        self.assertIn(
            'power.throttled_occurred === true ? "v2-service-warn"',
            js,
        )
        self.assertIn(
            'power.undervoltage_now === true ? "v2-service-bad"',
            js,
        )

    def test_systemd_and_hmi_labels_are_localized_in_presentation_only(self) -> None:
        js = (STATIC / "service-dashboard.js").read_text(encoding="utf-8")
        self.assertIn('active: "AKTYWNA"', js)
        self.assertIn('running: "DZIAŁA"', js)
        self.assertIn('green: "ZIELONY"', js)
        self.assertIn("localizeSystemdState(service.active_state)", js)
        self.assertIn("localizeSystemdSubstate(service.sub_state)", js)
        self.assertIn("localizeHmiColor(v2.hmi_color)", js)

    def test_service_layout_is_more_readable_and_uses_two_columns_on_1280_hmi(self) -> None:
        css = (STATIC / "service-dashboard.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 1400px)", css)
        self.assertIn(".v2-service-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }", css)
        self.assertIn(".v2-service-kv dt { color: var(--muted); font-size: .75rem; }", css)
        self.assertIn("font-size: .78rem;", css)
        self.assertIn("font-size: .73rem;", css)


if __name__ == "__main__":
    unittest.main()
