import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class WebDashboardStructureTest(unittest.TestCase):
    def test_root_dashboard_is_read_only_and_links_to_manual_control(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn('src="/dashboard-live.js"', html)
        self.assertIn('href="/dashboard.css"', html)
        self.assertIn('href="/control"', html)
        self.assertIn('id="openControlButton"', html)
        self.assertIn('id="dashboardSupplyRpm"', html)
        self.assertIn('id="dashboardExtractRpm"', html)
        self.assertIn('id="dashboardSupplyPercent"', html)
        self.assertIn('id="dashboardExtractPercent"', html)
        self.assertIn('id="dashboardAeroFan1"', html)
        self.assertIn('id="dashboardAeroFan2"', html)
        self.assertIn('id="weatherTemp"', html)
        self.assertIn('id="weatherIcon"', html)

        self.assertNotIn('id="applyFansButton"', html)
        self.assertNotIn('id="stopFansButton"', html)
        self.assertNotIn('data-aero-speed=', html)
        self.assertNotIn('src="/app.js"', html)
        self.assertNotIn('src="/tacho.js"', html)

    def test_dashboard_contains_both_sensor_zones_and_both_room_temperatures(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "airZone1Name", "airZone1Status", "airZone1Pm25", "airZone1Voc", "airZone1Nox",
            "airZone2Name", "airZone2Status", "airZone2Pm25", "airZone2Voc", "airZone2Nox",
            "insideTempZone1", "insideTempZone2", "outsideTemp",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertNotIn('id="airVerdict"', html)

    def test_dashboard_script_is_read_only_and_polls_weather(self):
        js = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")
        self.assertIn('requestJson("/api/v1/state")', js)
        self.assertIn('requestJson("/api/v1/config")', js)
        self.assertIn('requestJson("/api/v1/weather")', js)
        self.assertNotIn('/api/v1/manual/', js)
        self.assertNotIn('method:"POST"', js)
        self.assertNotIn('method: "POST"', js)
        self.assertIn('Math.round(n*10)', js)

    def test_manual_controls_live_only_on_control_page(self):
        html = (STATIC / "control.html").read_text(encoding="utf-8")
        self.assertIn('id="applyFansButton"', html)
        self.assertIn('id="stopFansButton"', html)
        self.assertIn('data-aero-speed="0"', html)
        self.assertIn('href="/"', html)
        self.assertIn('src="/app.js"', html)
        self.assertIn('src="/tacho.js"', html)

    def test_server_routes_root_control_and_live_dashboard_asset(self):
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(encoding="utf-8")
        self.assertIn('relative = "index.html"', server)
        self.assertIn('request_path in ("/control", "/control/")', server)
        self.assertIn('relative = "control.html"', server)
        self.assertIn('"dashboard-live.js"', server)
        self.assertIn('"dashboard.css"', server)
        self.assertIn('"control.html"', server)

    def test_dashboard_omits_development_helper_copy(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        css = (STATIC / "dashboard.css").read_text(encoding="utf-8")
        self.assertNotIn("ostatnio potwierdzony", html)
        self.assertNotIn("Dashboard read-only", html)
        self.assertNotIn("Kafel przygotowany", html)
        self.assertNotIn("oczekiwanie na integrację", html)
        self.assertIn(".air-zone-neutral { display: none; }", css)
        self.assertIn("#ecStatus { display: none; }", css)
        self.assertIn(".fan-drive", css)


if __name__ == "__main__":
    unittest.main()
