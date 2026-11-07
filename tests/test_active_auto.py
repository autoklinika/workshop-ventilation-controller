"""Active (actuating) AUTO verification with simulated core/actuators only."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from math import nan
from threading import Event, Thread
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from ventilation_core.application.active_auto import (
    ActiveWorkshopAuto, REQUIRED_APPROVAL_ITEMS, commissioning_approved, load_tuning
)
from ventilation_core.runtime.server import CoreServer
from ventilation_core.main import build_parser
from ventilation_core.web.app import WebApplication


def node(address, pm=8.0, temp=20.0, voc=100.0, nox=1.0, valid=True):
    return {
        "slave_address": address, "online": valid, "usable": valid,
        "measurement_valid": valid, "measurement_stale": not valid,
        "reading": {"pm2_5_ug_m3": pm, "voc_index": voc, "nox_index": nox,
                    "temperature_celsius": temp},
    }


def state(*, pm1=8, pm2=8, phase="INACTIVE", t1=20.0, t2=21.0):
    return {
        "mode": "STOP", "setpoints":{"supply_voltage": 0., "extract_voltage": 0.},
        "hardware_ready": True, "output_state_known": True, "active_alarms": [],
        "tacho": {"ready": True, "worker_alive": True,
                  "supply": {"valid":True,"rpm":600},
                  "extract": {"valid":True,"rpm":600}},
        "sensor_bus": {"nodes":[node(1,pm=pm1,temp=t1),node(2,pm=pm2,temp=t2)]},
        "calendar": {"phase":phase},
        "aero_bus": {"ready":True,"online":True,"usable":True,
                     "control_busy":False, "telemetry":{"fan_1_percent":0,"fan_2_percent":0}},
    }


class StubCore:
    def __init__(self, state):
        self.value=deepcopy(state)
        self.fan_calls=[]
        self.aero_calls=[]
        self.aero_succeeds=True

    def state(self):
        return SimpleNamespace(to_dict=lambda:deepcopy(self.value))

    def set_automatic(self, supply, extract):
        self.fan_calls.append((supply,extract))
        self.value["mode"]="AUTO"
        self.value["setpoints"]={"supply_voltage":supply,"extract_voltage":extract}
        return self.state()

    def control_aero(self, cmd):
        self.aero_calls.append((cmd.kind.value,cmd.value))
        if self.aero_succeeds:
            if cmd.kind.value == "airing":
                target=100 if cmd.value else 90
            else:
                target=cmd.value * 30
            self.value["aero_bus"]["telemetry"]["fan_1_percent"]=target
            self.value["aero_bus"]["telemetry"]["fan_2_percent"]=target
        return SimpleNamespace(succeeded=self.aero_succeeds,
                               physical_confirmation=self.aero_succeeds)


class ActiveWorkshopAutoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now=1_000.0
        self.hold_path=Path(self.tmp.name)/"auto-hold.json"
        self.auto=ActiveWorkshopAuto(enabled=True,hold_path=self.hold_path,clock=lambda:self.now,
                                     aero_min_interval=10,fan_min_interval=5)

    def test_off_by_default(self):
        self.assertFalse(build_parser().parse_args([]).enable_active_auto)
        disabled=ActiveWorkshopAuto(enabled=False,hold_path=self.hold_path,clock=lambda:self.now)
        core=StubCore(state())
        disabled.step(core)
        self.assertEqual(core.fan_calls,[])
        self.assertEqual(core.aero_calls,[])

    def test_idle_eco_is_nonzero_and_occupancy_normal(self):
        core=StubCore(state())
        self.auto.step(core)
        self.assertEqual(core.fan_calls,[(2.0,1.0)])
        self.assertEqual(core.aero_calls,[("speed",1)])
        self.assertEqual(self.auto.snapshot()["zones"]["ec"]["level"],"ECO")
        self.assertEqual(core.value["mode"],"AUTO")
        occupied=StubCore(state(phase="ACTIVE"))
        ctrl=ActiveWorkshopAuto(enabled=True,hold_path=self.hold_path,clock=lambda:self.now)
        ctrl.step(occupied)
        self.assertEqual(occupied.fan_calls,[(4.0,3.0)])

    def test_high_pm_without_calendar_window_runs_high_both_zones(self):
        core=StubCore(state(pm1=38,pm2=35))
        self.auto.step(core)
        self.assertEqual(core.fan_calls,[(9.0,6.0)])
        self.assertEqual(core.aero_calls,[("speed",3)])
        self.assertEqual(self.auto.snapshot()["zones"]["aero"]["level"],"HIGH")

    def test_cold_never_blocks_high_quality_demand(self):
        core=StubCore(state(pm1=31,pm2=20,t1=15))
        self.auto.step(core)
        self.assertEqual(core.fan_calls,[(9.0,6.0)])
        self.assertNotEqual(self.auto.snapshot()["zones"]["ec"]["reason"],"THERMAL_ECO_WHEN_AIR_NORMAL")

    def test_cold_normal_falls_to_background_not_stop(self):
        core=StubCore(state(phase="ACTIVE",t1=16))
        self.auto.step(core)
        self.assertEqual(core.fan_calls,[(2.0,1.0)])

    def test_sen55_loss_is_explicit_fallback_not_normal(self):
        s=state()
        s["sensor_bus"]["nodes"][0]=node(1,valid=False)
        s["sensor_bus"]["nodes"][1]=node(2,valid=False)
        core=StubCore(s)
        self.auto.step(core)
        self.assertEqual(core.fan_calls,[(4.0,3.0)])
        self.assertEqual(core.aero_calls,[("speed",2)])
        self.assertEqual(self.auto.snapshot()["zones"]["ec"]["level"],"SENSOR_FAULT")

    def test_higher_level_after_confirmation_and_slow_decay(self):
        core=StubCore(state())
        self.auto.step(core)
        self.now += 20
        core.value["sensor_bus"]["nodes"][0]["reading"]["pm2_5_ug_m3"] = 30
        self.auto.step(core)
        self.assertEqual(core.fan_calls,[(2.,1.)])
        self.now += 5.5
        self.auto.step(core)
        self.assertEqual(core.fan_calls[-1],(9.,6.))
        core.value["sensor_bus"]["nodes"][0]["reading"]["pm2_5_ug_m3"] = 7
        self.now+=10
        self.auto.step(core)
        self.assertEqual(core.fan_calls[-1],(9.,6.))
        self.now+=181
        self.auto.step(core)
        self.assertEqual(core.fan_calls[-1],(2.,1.))

    def test_tacho_failure_latches_hold_and_preserves_last_output(self):
        core=StubCore(state())
        self.auto.step(core)
        core.value["tacho"]["supply"]["valid"]=False
        core.value["tacho"]["supply"]["rpm"]=0
        self.now+=13
        self.auto.step(core)
        self.assertTrue(self.auto.snapshot()["hold"])
        self.assertIn("TACHO_SUPPLY",self.auto.snapshot()["hold_reason"])
        self.assertTrue(self.hold_path.is_file())
        self.assertEqual(core.fan_calls,[(2.,1.)])
        after_restart=ActiveWorkshopAuto(enabled=True,hold_path=self.hold_path)
        self.assertTrue(after_restart.paused)

    def test_operator_hold_and_resume_preflight(self):
        core=StubCore(state())
        self.auto.hold("MANUAL_COMMAND_stop")
        self.auto.step(core)
        self.assertEqual(core.fan_calls,[])
        s=state()
        s["hardware_ready"]=False
        with self.assertRaisesRegex(RuntimeError,"DAC"):
            self.auto.resume(s)
        self.auto.resume(state())
        self.assertFalse(self.auto.paused)
        self.assertFalse(self.hold_path.exists())

    def test_aero_unconfirmed_latches_hold(self):
        core=StubCore(state())
        core.aero_succeeds=False
        self.auto.step(core)
        self.assertTrue(self.auto.paused)
        self.assertIn("AERO_TARGET_PAIR_NOT_CONFIRMED",self.auto.last_error)

    def test_aero_requires_both_fans_not_just_first_delta(self):
        class OneFanSlow(StubCore):
            def control_aero(self, cmd):
                result = super().control_aero(cmd)
                self.value["aero_bus"]["telemetry"]["fan_2_percent"] = 0
                return result

        core=OneFanSlow(state())
        ctrl=ActiveWorkshopAuto(
            enabled=True,hold_path=self.hold_path,clock=lambda:self.now,
            aero_target_timeout_seconds=0.03,aero_target_poll_seconds=0.01)
        ctrl.step(core)
        self.assertTrue(ctrl.paused)
        self.assertEqual(core.aero_calls,[("speed",1)])
        self.assertIn("TARGET_PAIR_NOT_CONFIRMED",ctrl.last_error)

    def test_each_tacho_failure_mask_is_detected_without_unplugging_anything(self):
        for names in (("extract",),("supply",),("supply","extract")):
            with self.subTest(faulty=names):
                t=TemporaryDirectory()
                self.addCleanup(t.cleanup)
                c=ActiveWorkshopAuto(enabled=True,hold_path=Path(t.name)/"hold",
                                     clock=lambda:self.now)
                core=StubCore(state())
                c.step(core)
                for name in names:
                    core.value["tacho"][name]["valid"] = False
                    core.value["tacho"][name]["rpm"] = 0
                self.now+=13.0
                c.step(core)
                self.assertTrue(c.paused)
                self.assertIn("TACHO",c.pause_reason)
                self.assertEqual(core.fan_calls,[(2.0,1.0)])
                self.assertTrue(Path(t.name,"hold").is_file())

    def test_independent_tacho_supervision_runs_while_aero_command_waits(self):
        class SlowAero(StubCore):
            def __init__(self, s):
                super().__init__(s)
                self.started = Event()
                self.release = Event()
            def control_aero(self, cmd):
                self.started.set()
                assert self.release.wait(2.0), "test AERO command never released"
                return super().control_aero(cmd)

        core=SlowAero(state())
        thread=Thread(target=lambda:self.auto.step(core),daemon=True)
        thread.start()
        self.assertTrue(core.started.wait(1.0), "AERO command was not started")
        self.now += 13.0
        core.value["tacho"]["extract"]["valid"] = False
        core.value["tacho"]["extract"]["rpm"] = 0
        # This is a separate supervisory call from a different thread, NOT
        # another AERO actuator call.
        self.auto.supervise(core)
        self.assertTrue(self.auto.paused)
        self.assertIn("TACHO_EXTRACT", self.auto.pause_reason)
        core.release.set()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(core.aero_calls,[("speed",1)])

    def test_independent_supervision_holds_on_critical_alert(self):
        core=StubCore(state())
        self.auto.step(core)
        core.value["active_alarms"]=[{"severity":"critical","code":"TEST_CRITICAL"}]
        self.auto.supervise(core)
        self.assertTrue(self.auto.paused)
        self.assertEqual(self.auto.pause_reason,"CRITICAL_ALARM")

    def test_aero_max_requests_airing_after_high_speed(self):
        core=StubCore(state(pm1=65,pm2=65))
        self.auto.step(core)
        self.assertEqual(core.fan_calls,[(10.,7.)])
        self.assertEqual(core.aero_calls,[("speed",3)])
        self.now+=15
        self.auto.step(core)
        self.assertEqual(core.aero_calls[-1],("airing",1))
        self.assertEqual(core.value["aero_bus"]["telemetry"]["fan_1_percent"],100)

    def test_manual_commands_latch_hold_in_socket_dispatch(self):
        core=StubCore(state())
        class ManualStub(StubCore):
            def stop(self):
                self.value["mode"]="STOP"
                return self.state()
        svc=ManualStub(state())
        srv=CoreServer(service=svc,socket_path=Path(self.tmp.name)/"core.sock",
                       health_interval_seconds=1,auto_controller=self.auto)
        response=asyncio.run(srv._dispatch({"command":"stop"}))
        self.assertTrue(response["ok"])
        self.assertTrue(self.auto.paused)
        self.assertEqual(self.auto.pause_reason,"MANUAL_COMMAND_stop")

    def test_status_exposes_auto_state(self):
        core=StubCore(state())
        srv=CoreServer(service=core,socket_path=Path(self.tmp.name)/"core.sock",
                       health_interval_seconds=1,auto_controller=self.auto)
        r=asyncio.run(srv._dispatch({"command":"status"}))
        self.assertIn("active_auto",r["state"])
        self.assertEqual(r["state"]["active_auto"]["control_owner"],"ventilation-core")




class ActiveAutoProfileValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.profile=Path("config/active-auto-v1.json")
        self.template=Path("config/active-auto-commissioning.example.json")

    def test_checked_in_profile_is_valid(self):
        presets, limits, timings=load_tuning(self.profile)
        self.assertEqual(presets["HIGH"].supply_v,9.0)
        self.assertEqual(limits["pm2_5"],(15.,25.,50.))
        self.assertEqual(timings["decay_seconds"],180.0)

    def test_wrong_order_or_nan_rejected(self):
        doc=json.loads(self.profile.read_text(encoding="utf-8"))
        doc["presets"]["HIGH"]["supply_v"]=2.0
        p=Path(self.tmp.name)/"profile.json"
        p.write_text(json.dumps(doc),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"monotonic"):
            load_tuning(p)
        doc["presets"]["HIGH"]["supply_v"]=9.0
        doc["thresholds"]["pm2_5"]=[15.0,25.0,nan]
        p.write_text(json.dumps(doc),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"Invalid AUTO process"):
            load_tuning(p)

    def test_commissioning_template_does_not_grant_authority(self):
        ok,reason=commissioning_approved(self.template)
        self.assertFalse(ok)
        self.assertEqual(reason,"WORKSHOP_COMMISSIONING_EVIDENCE_INCOMPLETE")
        ok,reason=commissioning_approved(Path(self.tmp.name)/"missing")
        self.assertFalse(ok)
        self.assertEqual(reason,"WORKSHOP_COMMISSIONING_APPROVAL_MISSING")

    def test_commissioning_requires_each_evidence(self):
        p=Path(self.tmp.name)/"approval.json"
        data={"schema_version":1,"site":"WVC_WORKSHOP","approval":"APPROVED",
              "responsible_person":"operator",
              "evidence":{k:"test-evidence" for k in REQUIRED_APPROVAL_ITEMS}}
        p.write_text(json.dumps(data),encoding="utf-8")
        self.assertEqual(commissioning_approved(p),(True,""))
        data["evidence"]["tacho_fault_procedure"]=""
        p.write_text(json.dumps(data),encoding="utf-8")
        self.assertFalse(commissioning_approved(p)[0])

    def test_sensor_nan_is_never_treated_as_clean(self):
        s=state()
        s["sensor_bus"]["nodes"][0]["reading"]["pm2_5_ug_m3"]=nan
        core=StubCore(s)
        auto=ActiveWorkshopAuto(enabled=True,hold_path=Path(self.tmp.name)/"hold")
        auto.step(core)
        self.assertEqual(core.fan_calls,[(4.,3.)])
        self.assertEqual(auto.snapshot()["zones"]["ec"]["level"],"SENSOR_FAULT")

    def test_browser_api_uses_explicit_wvc_commands(self):
        class CoreClientFake:
            def __init__(self): self.requests=[]
            def request(self, payload):
                self.requests.append(payload)
                return {"ok":True,"active_auto":{"enabled":False}}
        core=CoreClientFake()
        web=WebApplication(core)
        self.assertEqual(web.handle("GET","/api/v1/auto").status,200)
        self.assertEqual(core.requests[-1],{"command":"auto-status"})
        # No unauthenticated HTTP endpoint may clear a latched safety HOLD.
        self.assertEqual(web.handle("POST","/api/v1/auto/hold").status,404)
        self.assertEqual(web.handle("POST","/api/v1/auto/resume").status,404)

if __name__ == "__main__":
    unittest.main()
