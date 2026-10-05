from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class CalendarUiContractTest(unittest.TestCase):
    def test_main_navigation_exposes_settings_without_enabling_generic_service(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/settings"', html)
        self.assertIn("USTAWIENIA", html)
        self.assertIn("SERWIS", html)

    def test_settings_page_uses_calendar_assets_and_explains_safety_boundary(self) -> None:
        html = (STATIC / "settings.html").read_text(encoding="utf-8")
        self.assertIn('href="/calendar.css"', html)
        self.assertIn('src="/calendar.js"', html)
        self.assertIn(
            "Calendar Engine nie steruje bezpośrednio wentylatorami ani AERO",
            html,
        )
        self.assertIn('id="calendarProfilesRows"', html)
        self.assertIn('id="calendarRulesRows"', html)
        self.assertIn("DATE_EXCEPTION &gt; DATE_RANGE &gt; SEASON &gt; WEEKLY &gt; DEFAULT", html)

    def test_calendar_browser_code_has_no_manual_control_endpoint(self) -> None:
        source = (STATIC / "calendar.js").read_text(encoding="utf-8")
        self.assertIn('api("/api/v1/calendar")', source)
        self.assertIn('api("/api/v1/calendar", {', source)
        self.assertNotIn("/api/v1/manual/", source)
        self.assertNotIn("/api/v1/command", source)
        self.assertNotIn("/api/v1/schedule", source)

    def test_static_server_keeps_calendar_assets_in_settings_shell(self) -> None:
        source = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"/settings", "/settings/"', source)
        self.assertIn('relative = "index.html"', source)
        self.assertIn('"settings.html"', source)
        self.assertIn('"calendar.css"', source)
        self.assertIn('"calendar.js"', source)
        self.assertNotIn('"schedule.css"', source)
        self.assertNotIn('"schedule.js"', source)


if __name__ == "__main__":
    unittest.main()
