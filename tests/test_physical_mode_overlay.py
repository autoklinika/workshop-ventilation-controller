from __future__ import annotations

from pathlib import Path
import unittest

from ventilation_core.web.app import WebApplication
from ventilation_core.web.server import _same_origin

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class CoreFake:
    def __init__(self, response=None):
        self.requests = []
        self.response = response

    def request(self, payload):
        self.requests.append(payload)
        if self.response is not None:
            return self.response
        if payload.get("command") == "auto-status":
            return {"ok": True, "active_auto": {"enabled": False, "active": False}}
        if payload.get("command") == "auto-resume":
            return {"ok": False, "error": "Active AUTO is not enabled in core configuration"}
        return {"ok": True, "active_auto": {"enabled": False, "hold": True}}


class PhysicalModeOverlayTest(unittest.TestCase):
    def test_manual_switch_one_click_no_pin(self):
        core = CoreFake()
        result = WebApplication(core).handle("POST", "/api/v1/physical-mode", {"mode": "MANUAL"})
        self.assertEqual(result.status, 200)
        self.assertEqual(core.requests, [{"command": "auto-manual"}])

    def test_auto_switch_one_click_still_uses_core_commissioning_gate(self):
        core = CoreFake()
        result = WebApplication(core).handle("POST", "/api/v1/physical-mode", {"mode": "AUTO"})
        self.assertEqual(result.status, 409)
        self.assertEqual(core.requests, [{"command": "auto-resume"}])
        self.assertIn("not enabled", result.payload["error"])

    def test_auto_enabled_core_accepts_without_pin_or_confirm(self):
        core = CoreFake({"ok": True, "active_auto": {"enabled": True, "active": True}})
        result = WebApplication(core).handle("POST", "/api/v1/physical-mode", {"mode": "AUTO"})
        self.assertEqual(result.status, 200)
        self.assertEqual(core.requests, [{"command": "auto-resume"}])

    def test_pin_credentials_or_confirmation_fields_are_not_accepted(self):
        invalid = (
            {"mode": "AUTO", "pin": "12345678"},
            {"mode": "AUTO", "pin": "12345678", "confirm": True},
            {"mode": "MANUAL", "pin": "12345678"},
            {"mode": "AUTO", "confirm": True},
            {"mode": "AUTO", "command": "set"},
            {"mode": "other"},
            {"mode": 1},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                core = CoreFake()
                result = WebApplication(core).handle("POST", "/api/v1/physical-mode", payload)
                self.assertEqual(result.status, 400)
                self.assertEqual(core.requests, [])

    def test_status_does_not_expose_any_pin_state(self):
        core = CoreFake()
        result = WebApplication(core).handle("GET", "/api/v1/auto")
        self.assertEqual(result.status, 200)
        self.assertEqual(core.requests, [{"command": "auto-status"}])
        self.assertNotIn("pin", str(result.payload).lower())

    def test_only_same_origin_operator_calls_are_accepted_by_transport(self):
        self.assertTrue(_same_origin("http://192.168.1.64:18091", "192.168.1.64:18091"))
        self.assertFalse(_same_origin("http://attacker.invalid", "192.168.1.64:18091"))
        self.assertFalse(_same_origin(None, "192.168.1.64:18091"))
        self.assertFalse(_same_origin("null", "192.168.1.64:18091"))

    def test_no_global_mode_banner_or_pin_anywhere_in_production_shell(self):
        index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="dashboardView"', index)
        self.assertIn('id="controlView"', index)
        self.assertIn('id="alertsView"', index)
        self.assertNotIn("wvc-mode-control", index)
        self.assertNotIn("wvcAutoPin", index)
        self.assertNotIn('src="/physical-mode.js"', index)
        self.assertNotIn('href="/physical-mode.css"', index)

    def test_toggle_adjacent_to_control_heading_not_separate_banner(self):
        control = (STATIC / "control.html").read_text(encoding="utf-8")
        header = control.split('<header class="topbar">',1)[1].split("</header>",1)[0]
        self.assertIn('id="wvcModeHeading">Sterowanie ręczne</h1>', header)
        self.assertIn('class="wvc-mode-toggle"', header)
        self.assertIn('id="wvcManualMode"', header)
        self.assertIn('id="wvcAutoMode"', header)
        self.assertNotIn("PIN", header)
        self.assertIn('id="stopFansButton"', control)
        self.assertIn('id="applyFansButton"', control)

    def test_switch_hydrates_with_strefy_not_in_dashboard(self):
        hydrate = (STATIC / "dashboard-live.js").read_text(encoding="utf-8")
        self.assertIn('loadV2Style("/physical-mode.css")', hydrate)
        self.assertIn('await loadV2Script("/physical-mode.js")', hydrate)
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(encoding="utf-8")
        self.assertIn('"physical-mode.js"', server)
        self.assertIn('"physical-mode.css"', server)

    def test_javascript_has_no_pin_and_writes_only_exact_mode_payload(self):
        script = (STATIC / "physical-mode.js").read_text(encoding="utf-8")
        self.assertIn("JSON.stringify({ mode })", script)
        self.assertIn('choose("MANUAL")', script)
        self.assertIn('choose("AUTO")', script)
        self.assertIn("/api/v1/state", script)
        self.assertNotIn("wvcAutoPin", script)
        self.assertNotIn("pin:", script)
        self.assertNotIn("confirm:", script)


if __name__ == "__main__":
    unittest.main()
