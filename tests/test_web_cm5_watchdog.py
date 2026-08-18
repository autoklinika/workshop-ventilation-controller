import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"
WEB = ROOT / "src" / "ventilation_core" / "web"


class WebCm5CommunicationWatchdogTest(unittest.TestCase):
    def test_watchdog_is_loaded_globally(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/cm5-watchdog.css"', html)
        self.assertIn('src="/cm5-watchdog.js"', html)

    def test_watchdog_uses_state_endpoint_and_fail_recovery_hysteresis(self):
        js = (STATIC / "cm5-watchdog.js").read_text(encoding="utf-8")
        self.assertIn("CM5_WATCHDOG_POLL_MS = 2000", js)
        self.assertIn("CM5_WATCHDOG_REQUEST_TIMEOUT_MS = 1500", js)
        self.assertIn("CM5_WATCHDOG_FAILURE_LIMIT = 3", js)
        self.assertIn("CM5_WATCHDOG_RECOVERY_LIMIT = 2", js)
        self.assertIn('fetch("/api/v1/state"', js)
        self.assertIn("controller.abort()", js)
        self.assertIn("cm5WatchdogFailures >= CM5_WATCHDOG_FAILURE_LIMIT", js)
        self.assertIn("cm5WatchdogRecoveries >= CM5_WATCHDOG_RECOVERY_LIMIT", js)

    def test_watchdog_blocks_gui_and_is_not_dismissible(self):
        js = (STATIC / "cm5-watchdog.js").read_text(encoding="utf-8")
        css = (STATIC / "cm5-watchdog.css").read_text(encoding="utf-8")
        self.assertIn("BRAK KOMUNIKACJI Z CM5", js)
        self.assertIn('element.setAttribute("inert", "")', js)
        self.assertIn('element.removeAttribute("inert")', js)
        self.assertIn('overlay.setAttribute("role", "alert")', js)
        self.assertIn("z-index:5000", css)
        self.assertIn("position:fixed", css)
        self.assertIn("inset:0", css)
        self.assertNotIn("button", js.lower())
        self.assertNotIn("backdrop-filter", css)

    def test_watchdog_is_read_only(self):
        js = (STATIC / "cm5-watchdog.js").read_text(encoding="utf-8")
        self.assertNotIn("POST", js)
        self.assertNotIn("/api/v1/manual/", js)
        self.assertNotIn("/api/v1/aero/", js)
        self.assertNotIn("/api/v1/stop", js)

    def test_server_serves_watchdog_assets(self):
        server = (WEB / "server.py").read_text(encoding="utf-8")
        self.assertIn('"cm5-watchdog.css"', server)
        self.assertIn('"cm5-watchdog.js"', server)


if __name__ == "__main__":
    unittest.main()
