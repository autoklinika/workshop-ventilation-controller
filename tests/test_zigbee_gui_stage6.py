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
        self.assertIn('"zigbee-stage13.css"', server)

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
        self.assertIn('apiPost("/api/v1/zigbee/pairing/ack"', script)
        self.assertIn('apiPost("/api/v1/zigbee/remove"', script)
        self.assertIn('apiPost("/api/v1/zigbee/remove-confirmation"', script)
        self.assertIn('fetch("/api/v1/zigbee/removal-confirmation"', script)
        self.assertIn('apiPost("/api/v1/zigbee/rename"', script)
        self.assertIn('apiPost("/api/v1/zigbee/role"', script)
        self.assertNotIn("window.confirm", script)
        self.assertNotIn("zigbee2mqtt/", script)
        self.assertNotIn("mosquitto", script.lower())
        self.assertNotIn("/api/v1/zigbee/publish", script)

    def test_gui_uses_one_inventory_list_for_all_sensor_roles_and_values(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn('role === "supply"', script)
        self.assertIn('return "NAWIEW"', script)
        self.assertIn('role === "extract"', script)
        self.assertIn('return "WYWIEW"', script)
        self.assertIn('role === "other"', script)
        self.assertIn('return "INNE"', script)
        self.assertIn("BEZ ROLI", script)
        self.assertIn('zigbee.sensor_list', script)
        self.assertIn("temperature_celsius", script)
        self.assertIn("humidity_percent", script)
        self.assertIn("battery_percent", script)
        self.assertIn("voltage_mv", script)
        self.assertIn("linkquality", script)
        self.assertIn("Ostatni pomiar", script)
        self.assertNotIn("zigbeeDeviceGrid", script)
        self.assertNotIn("Czujniki temperatury kanałów", script)

    def test_management_scope_is_visible_in_gui(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn("DODAJ URZĄDZENIE · 120 S", script)
        self.assertIn("ZAMKNIJ PAROWANIE", script)
        self.assertIn("ZMIEŃ NAZWĘ", script)
        self.assertIn("Rola systemowa", script)
        self.assertIn('<option value="other"', script)
        self.assertIn(">INNE</option>", script)
        self.assertIn("USUŃ", script)
        self.assertIn("POTWIERDŹ USUNIĘCIE", script)
        self.assertIn("CM5 · VENTILATION-CORE", script)
        self.assertIn("ZARZĄDZANIE PRZEZ VENTILATION-CORE", script)

    def test_periodic_refresh_does_not_replace_active_editor(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn("function editingControlActive()", script)
        self.assertIn("document.activeElement", script)
        self.assertIn('active.matches("input[data-zigbee-name-input],select[data-zigbee-role]")', script)
        self.assertIn("if (!force && editingControlActive()) return;", script)
        self.assertIn("currentState = payload.zigbee;", script)
        self.assertIn("setInterval(refresh, 3000)", script)

    def test_removal_confirmation_is_core_owned_not_browser_native(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn("confirmation_required", script)
        self.assertIn("confirmation.confirmation_id", script)
        self.assertIn("pollRemovalConfirmation", script)
        self.assertIn("currentRemovalConfirmation.last_error", script)
        self.assertNotIn("window.confirm", script)

    def test_pairing_result_is_only_a_client_view_of_core_capabilities(self) -> None:
        script = (STATIC / "zigbee-settings.js").read_text(encoding="utf-8")
        self.assertIn("URZĄDZENIE ZIGBEE ROZPOZNANE", script)
        self.assertIn("DOSTĘPNE DANE", script)
        self.assertIn("currentPairing.capabilities", script)
        self.assertIn('apiPost("/api/v1/zigbee/pairing/ack"', script)
        self.assertNotIn("OSTATNIO ODEBRANE", script.upper())
        self.assertNotIn("ostatnio odebrane", script.lower())


if __name__ == "__main__":
    unittest.main()
