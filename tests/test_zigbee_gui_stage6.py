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

    def test_zigbee_settings_uses_only_explicit_core_web_api(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/api/v1/zigbee"', script)
        self.assertIn('apiPost("/api/v1/zigbee/permit-join"', script)
        self.assertIn('apiPost("/api/v1/zigbee/remove"', script)
        self.assertIn('apiPost("/api/v1/zigbee/rename"', script)
        self.assertIn('apiPost("/api/v1/zigbee/role"', script)
        self.assertNotIn("zigbee2mqtt/", script)
        self.assertNotIn("mosquitto", script.lower())
        self.assertNotIn("/api/v1/zigbee/publish", script)

    def test_gui_exposes_both_semantic_channel_roles(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn('role === "supply"', script)
        self.assertIn('return "NAWIEW"', script)
        self.assertIn('role === "extract"', script)
        self.assertIn('return "WYWIEW"', script)
        self.assertIn("BEZ ROLI", script)
        self.assertIn("NIEPRZYPISANE", script)
        self.assertIn("temperature_celsius", script)
        self.assertIn("battery_percent", script)
        self.assertIn("linkquality", script)
        self.assertIn("parse_errors", script)

    def test_management_scope_is_visible_in_gui(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn("DODAJ URZĄDZENIE · 120 S", script)
        self.assertIn("ZAMKNIJ PAROWANIE", script)
        self.assertIn("ZMIEŃ NAZWĘ", script)
        self.assertIn("Rola systemowa", script)
        self.assertIn("USUŃ", script)
        self.assertIn("ZARZĄDZANIE PRZEZ VENTILATION-CORE", script)


if __name__ == "__main__":
    unittest.main()
