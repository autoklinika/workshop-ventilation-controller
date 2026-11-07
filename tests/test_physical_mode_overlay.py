from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ventilation_core.web.app import WebApplication
from ventilation_core.web.auto_mode_auth import AutoModePinVerifier, hashed_pin_record
from ventilation_core.web.server import _same_origin


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
            return {"ok": False, "error": "AUTO_NOT_COMMISSIONED"}
        return {"ok": True, "active_auto": {"enabled": False, "hold": True}}


class PhysicalModeOverlayTest(unittest.TestCase):
    def setUp(self):
        t = TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.file = Path(t.name) / "pin.json"
        self.auth = AutoModePinVerifier(self.file)

    def configure_pin(self):
        self.file.write_text(json.dumps(hashed_pin_record("12345678")), encoding="utf-8")
        self.file.chmod(0o600)

    def test_manual_handoff_does_not_need_pin(self):
        core = CoreFake()
        res = WebApplication(core, auto_mode_pin=self.auth).handle(
            "POST", "/api/v1/physical-mode", {"mode": "MANUAL"}
        )
        self.assertEqual(res.status, 200)
        self.assertEqual(core.requests, [{"command": "auto-manual"}])

    def test_auto_without_pin_file_fails_without_core_write(self):
        core = CoreFake()
        res = WebApplication(core, auto_mode_pin=self.auth).handle(
            "POST", "/api/v1/physical-mode",
            {"mode": "AUTO", "pin": "12345678", "confirm": True}
        )
        self.assertEqual(res.status, 503)
        self.assertEqual(core.requests, [])

    def test_invalid_auto_body_and_wrong_pin_never_reach_core(self):
        self.configure_pin()
        for item in (
            {"mode": "AUTO", "pin": "12345678"},
            {"mode": "AUTO", "pin": "12345678", "confirm": 1},
            {"mode": "AUTO", "pin": "12345678", "confirm": True, "command": "set"},
            {"mode": "MANUAL", "pin": "12345678"},
            {"mode": "AUTOMATIC"},
        ):
            core = CoreFake()
            self.assertEqual(
                WebApplication(core, auto_mode_pin=self.auth).handle(
                    "POST", "/api/v1/physical-mode", item
                ).status, 400
            )
            self.assertEqual(core.requests, [])
        core = CoreFake()
        self.assertEqual(
            WebApplication(core, auto_mode_pin=self.auth).handle(
                "POST", "/api/v1/physical-mode",
                {"mode": "AUTO", "pin": "99999999", "confirm": True}
            ).status, 403
        )
        self.assertEqual(core.requests, [])

    def test_correct_pin_does_not_bypass_core_commissioning(self):
        self.configure_pin()
        core = CoreFake()
        res = WebApplication(core, auto_mode_pin=self.auth).handle(
            "POST", "/api/v1/physical-mode",
            {"mode": "AUTO", "pin": "12345678", "confirm": True}
        )
        self.assertEqual(res.status, 409)
        self.assertFalse(res.payload["ok"])
        self.assertEqual(core.requests, [{"command": "auto-resume"}])
        self.assertNotIn("12345678", str(core.requests))

    def test_auto_status_has_only_boolean_pin_configuration(self):
        core = CoreFake()
        res = WebApplication(core, auto_mode_pin=self.auth).handle("GET", "/api/v1/auto")
        self.assertEqual(res.status, 200)
        self.assertFalse(res.payload["web_auto_pin_configured"])
        self.assertEqual(core.requests, [{"command": "auto-status"}])
        self.configure_pin()
        core2 = CoreFake()
        yes = WebApplication(core2, auto_mode_pin=self.auth).handle("GET", "/api/v1/auto")
        self.assertTrue(yes.payload["web_auto_pin_configured"])
        self.assertNotIn("salt_hex", str(yes.payload))
        self.assertNotIn("hash_hex", str(yes.payload))

    def test_cross_origin_post_rejected(self):
        self.assertTrue(_same_origin("http://192.168.1.64:18091", "192.168.1.64:18091"))
        self.assertFalse(_same_origin("http://malicious.invalid", "192.168.1.64:18091"))
        self.assertFalse(_same_origin(None, "192.168.1.64:18091"))
        self.assertFalse(_same_origin("null", "192.168.1.64:18091"))

    def test_real_dashboard_preserved_with_mode_selector(self):
        r = Path(__file__).resolve().parents[1] / "src" / "ventilation_core" / "web"
        shell = (r / "static/index.html").read_text(encoding="utf-8")
        server = (r / "server.py").read_text(encoding="utf-8")
        js = (r / "static/physical-mode.js").read_text(encoding="utf-8")
        self.assertIn('id="dashboardView"', shell)
        self.assertIn('id="controlView"', shell)
        self.assertIn('id="alertsView"', shell)
        self.assertIn('id="wvcManualMode"', shell)
        self.assertIn('id="wvcAutoMode"', shell)
        self.assertIn('id="wvcAutoPin"', shell)
        self.assertIn('id="wvcAutoConfirm"', shell)
        self.assertIn('src="/physical-mode.js"', shell)
        self.assertIn('href="/physical-mode.css"', shell)
        self.assertIn('"physical-mode.js"', server)
        self.assertIn('"physical-mode.css"', server)
        self.assertIn("/api/v1/physical-mode", js)
        self.assertIn('mode: "MANUAL"', js)
        self.assertIn('mode:"AUTO", pin:els.pin.value, confirm:true', js)


if __name__ == "__main__":
    unittest.main()
