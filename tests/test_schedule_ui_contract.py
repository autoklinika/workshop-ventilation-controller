from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class ScheduleUiContractTest(unittest.TestCase):
    def test_main_navigation_exposes_settings_without_enabling_generic_service(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/settings"', html)
        self.assertIn("USTAWIENIA", html)
        self.assertIn("SERWIS", html)

    def test_settings_page_uses_only_narrow_schedule_assets_and_explains_safety_boundary(self) -> None:
        html = (STATIC / "settings.html").read_text(encoding="utf-8")
        self.assertIn('href="/schedule.css"', html)
        self.assertIn('src="/schedule.js"', html)
        self.assertIn("Harmonogram nie steruje bezpośrednio wentylatorami ani AERO", html)
        self.assertIn('data-zone-editor="zone-1"', html)
        self.assertIn('data-zone-editor="zone-2"', html)

    def test_schedule_browser_code_has_no_manual_control_endpoint(self) -> None:
        source = (STATIC / "schedule.js").read_text(encoding="utf-8")
        self.assertIn('api("/api/v1/schedule")', source)
        self.assertIn('api("/api/v1/schedule/zone"', source)
        self.assertNotIn("/api/v1/manual/", source)
        self.assertNotIn("/api/v1/command", source)

    def test_static_server_keeps_settings_in_global_application_shell(self) -> None:
        source = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"/settings", "/settings/"', source)
        self.assertIn('relative = "index.html"', source)
        self.assertIn('"settings.html"', source)
        self.assertIn('"schedule.css"', source)
        self.assertIn('"schedule.js"', source)


if __name__ == "__main__":
    unittest.main()
