from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from ventilation_core.application.active_auto import ActiveWorkshopAuto
from ventilation_core.runtime.server import CoreServer
from ventilation_core.web.app import WebApplication
from ventilation_core.web.auto_mode_auth import (
    AutoModeAuthorizationError,
    AutoModePinVerifier,
    hashed_pin_record,
)


class CoreFake:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.value = {
            "mode": "STOP",
            "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
            "hardware_ready": True,
            "output_state_known": True,
            "active_alarms": [],
            "tacho": {"ready": True, "worker_alive": True},
            "aero_bus": {"usable": True},
            "sensor_bus": {"nodes": [
                {"slave_address": 1, "online": True, "usable": True,
                 "measurement_valid": True, "measurement_stale": False},
                {"slave_address": 2, "online": True, "usable": True,
                 "measurement_valid": True, "measurement_stale": False},
            ]},
        }

    def state(self):
        return SimpleNamespace(to_dict=lambda: dict(self.value))

    def request(self, message: dict):
        self.requests.append(message)
        return {"ok": True, "active_auto": {"enabled": True}}


class ModeSwitchTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.pin_file = self.temp / "pin.json"
        self.verifier = AutoModePinVerifier(self.pin_file)

    def set_pin(self, pin="12345678") -> None:
        self.pin_file.write_text(json.dumps(hashed_pin_record(pin)), encoding="utf-8")
        self.pin_file.chmod(0o600)

    def test_pin_creation_and_rotation(self):
        self.set_pin()
        self.assertTrue(self.verifier.configured)
        self.assertNotIn("12345678", self.pin_file.read_text())
        self.verifier.require("12345678")
        self.set_pin("87654321")
        self.verifier.require("87654321")
        with self.assertRaises(AutoModeAuthorizationError):
            self.verifier.require("12345678")

    def test_pin_file_must_be_private_and_pin_numeric(self):
        self.set_pin()
        self.pin_file.chmod(0o644)
        self.assertFalse(self.verifier.configured)
        with self.assertRaises(AutoModeAuthorizationError):
            self.verifier.require("12345678")
        with self.assertRaises(ValueError):
            hashed_pin_record("x" * 8)
        with self.assertRaises(ValueError):
            hashed_pin_record("1234")

    def test_brute_force_lockout(self):
        self.set_pin()
        for _ in range(4):
            with self.assertRaises(AutoModeAuthorizationError) as ctx:
                self.verifier.require("11111111")
            self.assertEqual(ctx.exception.status, 403)
        with self.assertRaises(AutoModeAuthorizationError) as ctx:
            self.verifier.require("11111111")
        self.assertEqual(ctx.exception.status, 429)
        with self.assertRaises(AutoModeAuthorizationError) as ctx:
            self.verifier.require("12345678")
        self.assertEqual(ctx.exception.status, 429)

    def test_http_origin_gate_blocks_cross_site_operator_control(self):
        from ventilation_core.web.server import _same_origin
        self.assertTrue(_same_origin("http://192.168.1.64:18091", "192.168.1.64:18091"))
        self.assertFalse(_same_origin("http://evil.invalid:18091", "192.168.1.64:18091"))
        self.assertFalse(_same_origin("null", "192.168.1.64:18091"))
        self.assertFalse(_same_origin(None, "192.168.1.64:18091"))

    def test_manual_web_switch_has_no_pin_and_only_manual_core_command(self):
        core=CoreFake()
        web=WebApplication(core,auto_mode_pin=self.verifier)
        response=web.handle("POST","/api/v1/physical-mode",{"mode":"MANUAL"})
        self.assertEqual(response.status,200)
        self.assertEqual(core.requests,[{"command":"auto-manual"}])

    def test_auto_web_resume_requires_pin_and_confirmation(self):
        self.set_pin()
        core=CoreFake()
        web=WebApplication(core,auto_mode_pin=self.verifier)
        for payload in (
            {"mode":"AUTO"},
            {"mode":"AUTO","pin":"12345678","confirm":False},
            {"mode":"AUTO","pin":"12345678","confirm":True,"command":"stop"},
        ):
            self.assertEqual(web.handle("POST","/api/v1/physical-mode",payload).status,400)
        self.assertEqual(core.requests,[])
        self.assertEqual(web.handle("POST","/api/v1/physical-mode",{"mode":"AUTO","pin":"22222222","confirm":True}).status,403)
        self.assertEqual(core.requests,[])
        response=web.handle("POST","/api/v1/physical-mode",{"mode":"AUTO","pin":"12345678","confirm":True})
        self.assertEqual(response.status,200)
        self.assertEqual(core.requests,[{"command":"auto-resume"}])
        self.assertNotIn("12345678",str(core.requests))

    def test_auto_http_is_fail_closed_without_pin_file(self):
        core=CoreFake()
        web=WebApplication(core,auto_mode_pin=self.verifier)
        response=web.handle("POST","/api/v1/physical-mode",{"mode":"AUTO","pin":"12345678","confirm":True})
        self.assertEqual(response.status,503)
        self.assertEqual(core.requests,[])

    def test_auto_readonly_status_exposes_configuration_not_pin(self):
        self.set_pin()
        core=CoreFake()
        web=WebApplication(core,auto_mode_pin=self.verifier)
        response=web.handle("GET","/api/v1/auto")
        self.assertEqual(response.status,200)
        self.assertEqual(response.payload["web_auto_pin_configured"],True)
        self.assertEqual(core.requests,[{"command":"auto-status"}])
        self.assertNotIn("hash",str(response.payload))

    def test_core_manual_hold_also_when_auto_disabled(self):
        core=CoreFake()
        ctrl=ActiveWorkshopAuto(enabled=False,hold_path=self.temp/"hold")
        server=CoreServer(service=core,socket_path=self.temp/"sock",health_interval_seconds=1,auto_controller=ctrl)
        out=asyncio.run(server._dispatch({"command":"auto-manual"}))
        self.assertTrue(out["ok"])
        self.assertTrue(out["active_auto"]["hold"])
        self.assertEqual(out["active_auto"]["mode"],"MANUAL")
        self.assertTrue((self.temp/"hold").exists())
        self.assertEqual(core.requests,[])
        self.assertEqual(core.value["setpoints"],{"supply_voltage":0.0,"extract_voltage":0.0})
        with self.assertRaisesRegex(RuntimeError,"not enabled"):
            asyncio.run(server._dispatch({"command":"auto-resume"}))

    def test_core_auto_resume_after_manual_requires_enabled_and_preflight(self):
        core=CoreFake()
        ctrl=ActiveWorkshopAuto(enabled=True,hold_path=self.temp/"hold")
        server=CoreServer(service=core,socket_path=self.temp/"sock",health_interval_seconds=1,auto_controller=ctrl)
        asyncio.run(server._dispatch({"command":"auto-manual"}))
        core.value["hardware_ready"]=False
        with self.assertRaisesRegex(RuntimeError,"DAC"):
            asyncio.run(server._dispatch({"command":"auto-resume"}))
        self.assertTrue(ctrl.paused)
        core.value["hardware_ready"]=True
        out=asyncio.run(server._dispatch({"command":"auto-resume"}))
        self.assertTrue(out["ok"])
        self.assertEqual(out["active_auto"]["mode"],"AUTO")

    def test_real_mode_ui_is_distinct_from_shadow_and_has_operator_controls(self):
        root=Path(__file__).resolve().parents[1]/"src"/"ventilation_core"/"web"/"static"
        html=(root/"automation.html").read_text()
        js=(root/"automation.js").read_text()
        self.assertIn('id="physicalModeValue"',html)
        self.assertIn('id="physicalManualBtn"',html)
        self.assertIn('id="physicalAutoBtn"',html)
        self.assertIn('id="physicalAutoPin"',html)
        self.assertIn('id="physicalAutoConfirm"',html)
        self.assertIn("AUTO (SHADOW)",html)
        self.assertIn("/api/v1/physical-mode",js)
        self.assertIn('JSON.stringify({mode:"MANUAL"})',js)
        self.assertIn('JSON.stringify({mode:"AUTO", pin:pin.value, confirm:true})',js)
        self.assertNotIn("12345678",js)


if __name__ == "__main__":
    unittest.main()
