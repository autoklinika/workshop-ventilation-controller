from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class ZoneDetailModalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.js = (STATIC / "zone-detail.js").read_text(encoding="utf-8")
        self.css = (STATIC / "zone-detail.css").read_text(encoding="utf-8")
        self.server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )

    def test_both_dashboard_zone_cards_open_detail_modal(self) -> None:
        self.assertIn('document.querySelector(".v2-zone-card.zone-one")', self.js)
        self.assertIn('document.querySelector(".v2-zone-card.zone-two")', self.js)
        self.assertIn('wireZoneDetailCard(', self.js)
        self.assertIn('openZoneDetailModal(zoneKey, card)', self.js)
        self.assertIn('id="zoneDetailClose"', self.js)

    def test_zone_modal_uses_same_large_window_and_fly_motion_pattern(self) -> None:
        self.assertIn("const ZONE_DETAIL_OPEN_MS = 280;", self.js)
        self.assertIn("const ZONE_DETAIL_CLOSE_MS = 240;", self.js)
        self.assertIn("zoneDetailTransformFromCard", self.js)
        self.assertIn("getBoundingClientRect()", self.js)
        self.assertIn("sourceCenterX - targetCenterX", self.js)
        self.assertIn("sourceCenterY - targetCenterY", self.js)
        self.assertIn("detailCard.animate(", self.js)
        self.assertIn("cubic-bezier(.18,.78,.18,1)", self.js)
        self.assertIn("cubic-bezier(.42,0,.72,.18)", self.js)
        self.assertIn("transform-origin:50% 50%;", self.css)

    def test_hmi_layout_fits_three_groups_on_1280x800_without_horizontal_scroll(self) -> None:
        self.assertIn("width:94vw;", self.css)
        self.assertIn("height:92vh;", self.css)
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr));", self.css)
        self.assertIn(".v2-zone-detail-body", self.css)
        body = self.css.split(".v2-zone-detail-body", 1)[1].split(".v2-zone-detail-group", 1)[0]
        self.assertIn("overflow:hidden", body)
        self.assertIn("backdrop-filter:blur(10px);", self.css)

    def test_zone1_exposes_all_current_sen55_ec_tacho_and_duct_measurements(self) -> None:
        for token in (
            "pm1_0_ug_m3",
            "pm2_5_ug_m3",
            "pm4_0_ug_m3",
            "pm10_0_ug_m3",
            "voc_index",
            "nox_index",
            "temperature_celsius",
            "humidity_percent",
            "supply_voltage",
            "extract_voltage",
            '"rpm"',
            '"frequency_hz"',
            'zoneDetailZigbeeByRole(state, "supply")',
            'zoneDetailZigbeeByRole(state, "extract")',
        ):
            self.assertIn(token, self.js)

    def test_zone2_exposes_sen55_and_aero_measurements_without_inventing_speed(self) -> None:
        for token in (
            "aero_bus",
            "supply_temperature_celsius",
            "extract_temperature_celsius",
            "outdoor_temperature_celsius",
            "fan_1_percent",
            "fan_2_percent",
            "last_control_result",
            '"target_value"',
            '"readback_value"',
            "Ostatnia wartość zadana",
        ):
            self.assertIn(token, self.js)
        self.assertNotIn("inferAero", self.js)
        self.assertNotIn("estimateAero", self.js)
        self.assertNotIn("fan_1_percent +", self.js)
        self.assertNotIn("fan_2_percent +", self.js)

    def test_zone_client_is_read_only_and_does_not_issue_control_commands(self) -> None:
        self.assertIn('zoneDetailGet("/api/v1/state")', self.js)
        self.assertIn('zoneDetailGet("/api/v1/config")', self.js)
        self.assertNotIn('method: "POST"', self.js)
        self.assertNotIn('method: "PUT"', self.js)
        self.assertNotIn('method: "PATCH"', self.js)
        self.assertNotIn('method: "DELETE"', self.js)
        self.assertNotIn("/api/v1/manual/", self.js)
        self.assertNotIn("/api/v1/alerts/ack", self.js)
        self.assertNotIn("/api/v1/schedule/zone", self.js)

    def test_modal_refreshes_live_values_only_while_open(self) -> None:
        self.assertIn("const ZONE_DETAIL_POLL_MS = 2000;", self.js)
        self.assertIn("window.setInterval(refreshZoneDetail, ZONE_DETAIL_POLL_MS)", self.js)
        self.assertIn("window.clearInterval(zoneDetailPollTimer)", self.js)
        self.assertIn("stopZoneDetailPolling();", self.js)

    def test_static_server_exposes_and_bundles_zone_assets(self) -> None:
        self.assertIn('"zone-detail.js"', self.server)
        self.assertIn('"zone-detail.css"', self.server)
        self.assertIn('relative == "ai-operator-view.js"', self.server)
        self.assertIn('relative == "ai-detail.css"', self.server)
        self.assertIn('for name in ("zone-detail.js", "history.js")', self.server)
        self.assertIn('for name in ("zone-detail.css", "history.css")', self.server)
        self.assertIn('module.read_bytes()', self.server)


if __name__ == "__main__":
    unittest.main()
