import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class WebDashboardStructureTest(unittest.TestCase):
    def test_root_dashboard_is_read_only_and_links_to_manual_control(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")

        self.assertIn('src="/dashboard.js"', html)
        self.assertIn('href="/control"', html)
        self.assertIn('id="openControlButton"', html)
        self.assertIn('id="dashboardSupplyRpm"', html)
        self.assertIn('id="dashboardExtractRpm"', html)
        self.assertIn('id="dashboardAeroFan1"', html)
        self.assertIn('id="dashboardAeroFan2"', html)
        self.assertIn('id="weatherTemp"', html)

        self.assertNotIn('id="applyFansButton"', html)
        self.assertNotIn('id="stopFansButton"', html)
        self.assertNotIn('data-aero-speed=', html)
        self.assertNotIn('src="/app.js"', html)
        self.assertNotIn('src="/tacho.js"', html)

    def test_dashboard_script_has_no_manual_control_endpoint(self):
        js = (STATIC / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn('requestJson("/api/v1/state")', js)
        self.assertIn('requestJson("/api/v1/config")', js)
        self.assertNotIn('/api/v1/manual/', js)
        self.assertNotIn('method: "POST"', js)
        self.assertIn('state.air_quality.zone1.status', js)
        self.assertIn('environment.outdoor_temperature_celsius', js)

    def test_manual_controls_live_only_on_control_page(self):
        html = (STATIC / "control.html").read_text(encoding="utf-8")

        self.assertIn('id="applyFansButton"', html)
        self.assertIn('id="stopFansButton"', html)
        self.assertIn('data-aero-speed="0"', html)
        self.assertIn('href="/"', html)
        self.assertIn('src="/app.js"', html)
        self.assertIn('src="/tacho.js"', html)

    def test_server_routes_root_and_control_separately(self):
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('relative = "index.html"', server)
        self.assertIn('request_path in ("/control", "/control/")', server)
        self.assertIn('relative = "control.html"', server)
        self.assertIn('"dashboard.js"', server)
        self.assertIn('"control.html"', server)

    def test_weather_is_placeholder_not_fabricated_data(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "dashboard.js").read_text(encoding="utf-8")

        self.assertIn("Brak danych pogodowych", html)
        self.assertIn("Źródło internetowej pogody dodamy w osobnym etapie", html)
        self.assertNotIn("open-meteo", js.lower())
        self.assertNotIn("weatherapi", js.lower())


if __name__ == "__main__":
    unittest.main()
