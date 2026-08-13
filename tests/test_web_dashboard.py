import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class WebDashboardV2StructureTest(unittest.TestCase):
    def test_v2_root_is_read_only_and_links_to_service_control(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("PULPIT WARSZTATU", html)
        self.assertIn('src="/dashboard-live.js"', html)
        self.assertIn('href="/dashboard.css"', html)
        self.assertIn('href="/control"', html)
        self.assertIn("AUTOKLINIKA", html)
        self.assertIn("STREFY", html)
        self.assertIn("HISTORIA", html)
        self.assertIn("ALARMY", html)
        self.assertIn("USTAWIENIA", html)
        self.assertIn("SERWIS", html)
        self.assertNotIn('class="v2-footer-status"', html)
        self.assertNotIn('id="footerCore"', html)
        self.assertNotIn('id="footerTacho"', html)
        self.assertNotIn('id="footerSensor"', html)
        self.assertNotIn('id="footerAero"', html)
        self.assertNotIn('id="footerUptime"', html)
        self.assertNotIn('id="applyFansButton"', html)
        self.assertNotIn('id="stopFansButton"', html)
        self.assertNotIn('data-aero-speed=', html)
        self.assertNotIn('src="/app.js"', html)
        self.assertNotIn('src="/tacho.js"', html)

    def test_v2_contains_live_zone_and_aero_fields(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "zone1Name", "zone2Name",
            "zone1AirStatus", "zone2AirStatus",
            "zone1Voc", "zone2Voc", "zone1Pm25", "zone2Pm25",
            "zone1VentilationPercent", "zone1SupplyPercent", "zone1ExtractPercent",
            "zone2AeroMode", "zone2AeroSupply", "zone2AeroExtract",
        ):
            self.assertIn(f'id="{element_id}"', html)

    def test_v2_history_and_events_are_explicit_placeholders(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("TRENDY", html)
        self.assertIn("OSTATNIE 24H", html)
        self.assertIn("oczekiwanie na integrację danych historycznych", html)
        self.assertIn("Brak historii zdarzeń", html)

    def test_v2_script_is_read_only(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")
        self.assertIn('/api/v1/state', js)
        self.assertIn('/api/v1/config', js)
        self.assertIn('/api/v1/weather', js)
        self.assertNotIn('/api/v1/manual/', js)
        self.assertNotIn('method:"POST"', js)
        self.assertNotIn('method: "POST"', js)
        self.assertIn("Math.round(n*10)", js)
        self.assertNotIn("footerCore", js)
        self.assertNotIn("footerTacho", js)
        self.assertNotIn("footerSensor", js)
        self.assertNotIn("footerAero", js)
        self.assertNotIn("footerUptime", js)

    def test_manual_controls_remain_on_control_page(self):
        html = (STATIC / "control.html").read_text(encoding="utf-8")
        self.assertIn('id="applyFansButton"', html)
        self.assertIn('id="stopFansButton"', html)
        self.assertIn('data-aero-speed="0"', html)
        self.assertIn('src="/app.js"', html)
        self.assertIn('src="/tacho.js"', html)

    def test_control_page_uses_native_v2_shell_without_runtime_reflow(self):
        html = (STATIC / "control.html").read_text(encoding="utf-8")
        js = (STATIC / "tacho.js").read_text(encoding="utf-8")
        css = (STATIC / "sidebar.css").read_text(encoding="utf-8")
        self.assertIn('href="/sidebar.css"', html)
        self.assertIn('class="v2-topbar"', html)
        self.assertIn('class="v2-sidebar"', html)
        self.assertIn('class="v2-main"', html)
        self.assertNotIn('class="app-sidebar"', html)
        self.assertNotIn('class="with-sidebar"', html)
        self.assertNotIn("upgradeControlToV2Shell", js)
        self.assertIn(".v2-main>.app-shell{width:100%;max-width:none;margin:0;padding:0}", css)
        self.assertIn(".v2-nav.active{margin:0 0 4px", css)

    def test_v2_css_contains_reference_shell(self):
        css = (STATIC / "dashboard.css").read_text(encoding="utf-8")
        for selector in (
            ".v2-topbar", ".v2-sidebar", ".v2-zone-card",
            ".v2-unit-card", ".v2-lower-grid",
        ):
            self.assertIn(selector, css)


if __name__ == "__main__":
    unittest.main()
