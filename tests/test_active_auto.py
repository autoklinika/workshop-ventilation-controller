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
        self.stop_calls=0

    def state(self):
        return SimpleNamespace(to_dict=lambda:deepcopy(self.value))

    def set_automatic(self, supply, extract):
        self.fan_calls.append((supply,extract))
        self.value["mode"]="AUTO"
        self.value["setpoints"]={"supply_voltage":supply,"extract_voltage":extract}
        return self.state()

    def stop(self):
        self.stop_calls += 1
        self.value["mode"] = "STOP"
        self.value["setpoints"] = {"supply_voltage": 0.0, "extract_voltage": 0.0}
        self.value["tacho"]["supply"]["rpm"] = 0.0
        self.value["tacho"]["extract"]["rpm"] = 0.0
        self.value["tacho"]["supply"]["valid"] = False
        self.value["tacho"]["extract"]["valid"] = False
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
        self.auto=ActiveWorkshopAuto(startup_manual_hold=False,enabled=True,hold_path=self.hold_path,clock=lambda:self.now,
                                     aero_min_interval=10,fan_min_interval=5)

    def test_enabled_production_default_boots_in_persistent_manual(self):
        ctrl=ActiveWorkshopAuto(enabled=True,hold_path=self.hold_path)
        self.assertTrue(ctrl.paused)
        self.assertEqual(ctrl.pause_reason,"BOOT_MANUAL_REQUIRES_EXPLICIT_AUTO_RESUME")
        self.assertTrue(self.hold_path.is_file())
        restored=ActiveWorkshopAuto(enabled=True,hold_path=self.hold_path)
        self.assertTrue(restored.paused)
        self.assertEqual(restored.snapshot()["mode"],"MANUAL")

    def test_off_by_default(self):
        self.assertFalse(build_parser().parse_args([]).enable_active_auto)
        disabled=ActiveWorkshopAuto(startup_manual_hold=False,enabled=False,hold_path=self.hold_path,clock=lambda:self.now)
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
        ctrl=ActiveWorkshopAuto(startup_manual_hold=False,enabled=True,hold_path=self.hold_path,clock=lambda:self.now)
        ctrl.step(occupied)
        self.assertEqual(occupied.fan_calls,[(4.0,3.0)])

    def test_max_threshold_is_strictly_above_70_pm25(self):
        for pm, expected_ec, expected_level in (
            (69.9, (9.0, 6.0), "HIGH"),
            (70.0, (9.0, 6.0), "HIGH"),
            (70.1, (10.0, 7.0), "MAX"),
        ):
            with self.subTest(pm=pm), TemporaryDirectory() as tmp:
                ctrl = ActiveWorkshopAuto(
                    enabled=True,
                    startup_manual_hold=False,
                    hold_path=Path(tmp)/"hold.json",
                    profile_path=Path("config/active-auto-v1.json"),
                )
                core = StubCore(state(pm1=pm, pm2=pm))
                ctrl.step(core)
                self.assertEqual(core.fan_calls, [expected_ec])
                self.assertEqual(core.aero_calls, [("speed", 3)])
                self.assertEqual(ctrl.snapshot()["zones"]["ec"]["level"], expected_level)
                self.assertEqual(ctrl.snapshot()["zones"]["aero"]["level"], expected_level)

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

    def test_sen55_loss_switches_to_manual_without_replacing_commands(self):
        core=StubCore(state())
        core.value["sensor_bus"]["nodes"][0]=node(1,valid=False)
        core.value["sensor_bus"]["nodes"][1]=node(2,valid=False)
        self.auto.step(core)
        snap=self.auto.snapshot()
        self.assertEqual(snap["mode"],"MANUAL")
        self.assertTrue(snap["hold"])
        self.assertEqual(snap["hold_reason"],"SEN55_1_2_UNAVAILABLE")
        self.assertFalse(snap["fault_latched"])  # Manual must not be PIN/ACK locked.
        self.assertEqual(snap["operator_action"],"STOP_HAZARDOUS_WORK_AND_CHECK_VENTILATION")
        self.assertEqual(core.fan_calls,[])
        self.assertEqual(core.aero_calls,[])
        self.assertEqual(core.stop_calls,0)
        self.assertTrue(self.hold_path.exists())

    def test_each_sen55_loss_retains_high_outputs_and_requires_explicit_auto(self):
        for missing in ((1,), (2,), (1,2)):
            with self.subTest(missing=missing), TemporaryDirectory() as tmp:
                hold=Path(tmp)/"sensor-hold.json"
                ctrl=ActiveWorkshopAuto(
                    enabled=True,startup_manual_hold=False,hold_path=hold,
                    clock=lambda:self.now)
                core=StubCore(state(pm1=75,pm2=75))
                ctrl.step(core)
                self.assertEqual(core.fan_calls,[(10.0,7.0)])
                self.assertEqual(core.aero_calls,[("speed",3)])
                before_setpoints=dict(core.value["setpoints"])
                before_aero=dict(core.value["aero_bus"]["telemetry"])
                for address in missing:
                    core.value["sensor_bus"]["nodes"][address-1]=node(address,valid=False)
                ctrl.supervise(core)
                snap=ctrl.snapshot()
                self.assertEqual(snap["mode"],"MANUAL")
                self.assertEqual(snap["hold_reason"],"SEN55_"+"_".join(map(str,missing))+"_UNAVAILABLE")
                self.assertFalse(snap["fault_latched"])
                self.assertEqual(core.value["setpoints"],before_setpoints)
                self.assertEqual(core.value["aero_bus"]["telemetry"],before_aero)
                self.assertEqual(core.stop_calls,0)
                ctrl.step(core)
                self.assertEqual(core.fan_calls,[(10.0,7.0)])
                self.assertEqual(core.aero_calls,[("speed",3)])
                restored=ActiveWorkshopAuto(
                    enabled=True,startup_manual_hold=False,hold_path=hold)
                self.assertEqual(restored.snapshot()["mode"],"MANUAL")
                with self.assertRaisesRegex(RuntimeError,"SEN55"):
                    restored.resume(core.value)
                for address in missing:
                    core.value["sensor_bus"]["nodes"][address-1]=node(address)
                restored.step(core)
                self.assertEqual(core.fan_calls,[(10.0,7.0)])  # No silent restart.
                restored.resume(core.value)
                self.assertFalse(restored.paused)

    def test_aero_connection_failure_transfers_to_manual(self):
        core=StubCore(state())
        core.value["aero_bus"]["online"]=False
        self.auto.step(core)
        self.assertEqual(self.auto.snapshot()["mode"],"MANUAL")
        self.assertEqual(self.auto.snapshot()["hold_reason"],"AERO_UNAVAILABLE")
        self.assertEqual(core.fan_calls,[])
        self.assertEqual(core.aero_calls,[])
        self.assertEqual(core.stop_calls,0)

    def test_aero_connection_failure_detected_by_separate_supervisor(self):
        core=StubCore(state(pm1=75,pm2=75))
        self.auto.step(core)
        before=list(core.fan_calls)
        core.value["aero_bus"]["usable"]=False
        self.auto.supervise(core)
        self.assertEqual(self.auto.snapshot()["mode"],"MANUAL")
        self.assertEqual(self.auto.snapshot()["hold_reason"],"AERO_UNAVAILABLE")
        self.assertEqual(core.fan_calls,before)

    def test_operator_manual_commands_remain_available_after_latched_tacho_fault(self):
        class ManualEnabled(StubCore):
            def set_manual(self, supply, extract):
                self.value["mode"]="MANUAL"
                self.value["setpoints"]={
                    "supply_voltage":supply,"extract_voltage":extract}
                return self.state()

        core=ManualEnabled(state())
        self.auto.hold("TACHO_SUPPLY_FEEDBACK_MISSING",fault=True,fault_mask="SUPPLY")
        srv=CoreServer(service=core,socket_path=Path(self.tmp.name)/"core.sock",
                       health_interval_seconds=1,auto_controller=self.auto)
        response=asyncio.run(srv._dispatch({
            "command":"set","supply_voltage":4.0,"extract_voltage":3.0}))
        self.assertTrue(response["ok"])
        self.assertEqual(core.value["setpoints"],{
            "supply_voltage":4.0,"extract_voltage":3.0})
        self.assertTrue(self.auto.snapshot()["fault_latched"])  # Only AUTO gated.
        self.assertEqual(self.auto.snapshot()["mode"],"MANUAL")
        self.assertTrue(asyncio.run(srv._dispatch({"command":"stop"}))["ok"])
        self.assertEqual(core.value["setpoints"],{
            "supply_voltage":0.0,"extract_voltage":0.0})

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

    def test_tacho_failure_stops_both_ec_and_requires_local_acknowledgement(self):
        core=StubCore(state())
        self.auto.step(core)
        core.value["tacho"]["supply"]["valid"]=False
        core.value["tacho"]["supply"]["rpm"]=0
        self.now+=13
        self.auto.supervise(core)
        self.assertFalse(self.auto.paused)  # confirmation grace, not yet 4 s
        self.now+=4.1
        self.auto.supervise(core)
        self.assertTrue(self.auto.snapshot()["hold"])
        self.assertTrue(self.auto.snapshot()["fault_latched"])
        self.assertEqual(self.auto.snapshot()["fault_mask"],"SUPPLY")
        self.assertEqual(core.stop_calls,1)
        self.assertEqual(core.value["setpoints"],{"supply_voltage":0.0,"extract_voltage":0.0})
        with self.assertRaisesRegex(RuntimeError,"local service acknowledgement"):
            self.auto.resume(core.state().to_dict())
        after_restart=ActiveWorkshopAuto(startup_manual_hold=False,enabled=True,hold_path=self.hold_path)
        self.assertTrue(after_restart.paused)
        self.assertTrue(after_restart.snapshot()["fault_latched"])
        after_restart.acknowledge_fault(core.state().to_dict())
        self.assertTrue(after_restart.paused)  # acknowledgement does not resume AUTO
        self.assertFalse(after_restart.snapshot()["fault_latched"])
        after_restart.resume(core.state().to_dict())
        self.assertFalse(after_restart.paused)

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
        ctrl=ActiveWorkshopAuto(startup_manual_hold=False,
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
                c=ActiveWorkshopAuto(startup_manual_hold=False,enabled=True,hold_path=Path(t.name)/"hold",
                                     clock=lambda:self.now)
                core=StubCore(state())
                c.step(core)
                for name in names:
                    core.value["tacho"][name]["valid"] = False
                    core.value["tacho"][name]["rpm"] = 0
                self.now+=13.0
                c.supervise(core)
                self.now+=4.1
                c.supervise(core)
                self.assertTrue(c.paused)
                self.assertIn("TACHO",c.pause_reason)
                self.assertTrue(c.snapshot()["fault_latched"])
                self.assertEqual(core.stop_calls,1)
                self.assertEqual(core.value["setpoints"],{"supply_voltage":0.0,"extract_voltage":0.0})
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
        self.assertFalse(self.auto.paused)
        self.now += 4.1
        self.auto.supervise(core)
        self.assertTrue(self.auto.paused)
        self.assertIn("TACHO_EXTRACT", self.auto.pause_reason)
        self.assertEqual(core.stop_calls,1)
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

    def test_operator_manual_takes_over_while_aero_is_busy(self):
        class SlowAero(StubCore):
            def __init__(self, s):
                super().__init__(s)
                self.started, self.release = Event(), Event()
            def control_aero(self, cmd):
                self.started.set()
                assert self.release.wait(2), "AERO test timed out"
                return super().control_aero(cmd)

        core=SlowAero(state())
        writer=Thread(target=lambda: self.auto.step(core),daemon=True)
        writer.start()
        self.assertTrue(core.started.wait(1))
        server=CoreServer(service=core,socket_path=Path(self.tmp.name)/"core.sock",
                          health_interval_seconds=1,auto_controller=self.auto)
        response=asyncio.run(server._dispatch({"command":"auto-manual"}))
        self.assertTrue(response["ok"])
        self.assertEqual(self.auto.snapshot()["mode"],"MANUAL")
        self.assertEqual(self.auto.snapshot()["hold_reason"],"OPERATOR_SELECTED_MANUAL")
        core.release.set()
        writer.join(timeout=2)
        self.assertFalse(writer.is_alive())
        before=list(core.fan_calls)
        self.auto.step(core)
        self.assertEqual(core.fan_calls,before)

    def test_tacho_stop_write_failure_stays_fault_latched(self):
        class FaultyStop(StubCore):
            def stop(self):
                self.stop_calls += 1
                raise RuntimeError("I2C DAC unavailable")

        core=FaultyStop(state())
        self.auto.step(core)
        core.value["tacho"]["extract"]["valid"]=False
        core.value["tacho"]["extract"]["rpm"]=0
        self.now+=13
        self.auto.supervise(core)
        self.now+=4.1
        self.auto.supervise(core)
        self.assertTrue(self.auto.snapshot()["fault_latched"])
        self.assertIn("EC_STOP_FAILED",self.auto.snapshot()["last_error"])
        self.assertTrue(self.hold_path.exists())

    def test_aero_max_requests_airing_after_high_speed(self):
        core=StubCore(state(pm1=75,pm2=75))
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
        self.assertEqual(limits["pm2_5"],(15.,25.,70.))
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
        auto=ActiveWorkshopAuto(startup_manual_hold=False,enabled=True,hold_path=Path(self.tmp.name)/"hold")
        auto.step(core)
        self.assertEqual(core.fan_calls,[])
        self.assertEqual(core.aero_calls,[])
        self.assertEqual(auto.snapshot()["mode"],"MANUAL")
        self.assertEqual(auto.snapshot()["hold_reason"],"SEN55_1_UNAVAILABLE")
        with self.assertRaisesRegex(RuntimeError, "SEN55"):
            auto.resume(core.value)

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
