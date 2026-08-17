import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"
SERVER = ROOT / "src" / "ventilation_core" / "web" / "server.py"


class ZigbeeGuiStage6Tests(unittest.TestCase):
    def test_settings_route_and_assets_are_served(self) -> None:
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn('"/settings"', server)
        self.assertIn('"zigbee-settings.js"', server)
        self.assertIn('"zigbee-settings.css"', server)

    def test_sidebar_settings_navigation_is_enabled_by_v2_router(self) -> None:
        dashboard = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")
        self.assertIn('textContent.trim() === "USTAWIENIA"', dashboard)
        self.assertIn('settings.href = "/settings"', dashboard)
        self.assertIn('settings.dataset.route = "/settings"', dashboard)
        self.assertIn('path.startsWith("/settings")', dashboard)

    def test_zigbee_settings_reads_only_authoritative_web_api(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/api/v1/zigbee"', script)
        self.assertNotIn("zigbee2mqtt/", script)
        self.assertNotIn("permit_join", script)
        self.assertNotIn('method: "POST"', script)
        self.assertNotIn("mosquitto", script.lower())

    def test_gui_exposes_both_semantic_channel_roles(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn('role === "supply"', script)
        self.assertIn('return "NAWIEW"', script)
        self.assertIn('role === "extract"', script)
        self.assertIn('return "WYWIEW"', script)
        self.assertIn("temperature_celsius", script)
        self.assertIn("battery_percent", script)
        self.assertIn("linkquality", script)
        self.assertIn("parse_errors", script)

    def test_read_only_scope_is_visible_in_gui(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn("TRYB TYLKO DO ODCZYTU", script)
        self.assertIn("GUI nie łączy się bezpośrednio z MQTT ani Zigbee2MQTT", script)


if __name__ == "__main__":
    unittest.main()
