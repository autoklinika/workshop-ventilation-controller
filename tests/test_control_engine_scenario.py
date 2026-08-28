from __future__ import annotations

import unittest

from ventilation_core.application.control_engine_scenario import ControlEngineScenarioRunner


LAB_TUNING = {
    "normal_air_request_pct": 20.0,
    "boost_air_request_pct": 40.0,
    "high_air_request_pct": 70.0,
    "max_air_request_pct": 100.0,
    "thermal_normal_limit_pct": 100.0,
    "thermal_limiting_limit_pct": 60.0,
    "thermal_minimum_limit_pct": 30.0,
    "thermal_protection_limit_pct": 10.0,
    "extract_bias_pct": 5.0,
    "aero_normal_speed": 0,
    "aero_boost_speed": 1,
    "aero_high_speed": 2,
    "aero_max_speed": 3,
    "pm2_5_hysteresis_ug_m3": 2.0,
    "voc_hysteresis_index": 10.0,
    "nox_hysteresis_index": 5.0,
    "temperature_hysteresis_celsius": 1.0,
    "pm2_5_boost_confirmation_seconds": 30.0,
    "state_minimum_hold_seconds": 60.0,
    "boost_decay_seconds": 120.0,
    "sensor_fallback_supply_pct": 45.0,
    "sensor_fallback_extract_pct": 50.0,
    "aero_sensor_fallback_speed": 2,
}


def control_engine_config() -> dict:
    return {
        "schema_version": 1,
        "policy": {
            "version": "scenario-lab-only-v1",
            "pm2_5_reference_ug_m3": 15.0,
            "pm2_5_high_ug_m3": 25.0,
            "pm2_5_max_ug_m3": 50.0,
            "pm10_reference_ug_m3": 45.0,
            "voc_boost_index": 150.0,
            "voc_high_index": 200.0,
            "voc_max_index": 300.0,
            "nox_boost_index": 10.0,
            "nox_high_index": 50.0,
            "nox_max_index": 100.0,
            "temperature_normal_above_celsius": 20.0,
            "temperature_limiting_from_celsius": 18.0,
            "temperature_minimum_from_celsius": 16.0,
            "tuning": dict(LAB_TUNING),
        },
    }


def sensor(*, pm=5.0, pm10=8.0, voc=100.0, nox=1.0, temp=22.0, usable=True):
    return {
        "usable": usable,
        "pm2_5_ug_m3": pm,
        "pm10_0_ug_m3": pm10,
        "voc_index": voc,
        "nox_index": nox,
        "temperature_celsius": temp,
    }


def calendar(*, phase="ACTIVE", mode="AUTO", supply=30.0, extract=35.0):
    return {
        "phase": phase,
        "mode": mode,
        "profile": "SCENARIO_LAB",
        "schedule_supply_pct": supply,
        "schedule_extract_pct": extract,
        "schedule_request_source": "SCENARIO",
    }


def step(at, *, s1=None, s2=None, cal=None, zigbee_supply=None, **extra):
    return {
        "at_seconds": at,
        "calendar": cal or calendar(),
        "sensor_1": s1 or sensor(),
        "sensor_2": s2 or sensor(),
        "zigbee_supply": zigbee_supply or {
            "temperature_celsius": 10.0,
            "age_seconds": 0.0,
            "available": True,
            "timestamp_available": True,
        },
        "zigbee_extract": {
            "temperature_celsius": 20.0,
            "age_seconds": 0.0,
            "available": True,
            "timestamp_available": True,
        },
        **extra,
    }


def scenario(steps):
    return {
        "schema_version": 1,
        "name": "synthetic-lab-regression",
        "start_utc": "2026-01-15T08:00:00+00:00",
        "control_engine": control_engine_config(),
        "steps": steps,
    }


def zone(result, step_index, sensor_address):
    rows = result.to_dict()["steps"][step_index]["shadow"]["zones"]
    return next(row for row in rows if row["sensor_address"] == sensor_address)


class ControlEngineScenarioRunnerTest(unittest.TestCase):
    def test_pm_confirmation_immediate_high_and_delayed_decay(self):
        result = ControlEngineScenarioRunner().run(
            scenario(
                [
                    step(0),
                    step(10, s1=sensor(pm=16.0)),
                    step(39, s1=sensor(pm=16.0)),
                    step(40, s1=sensor(pm=16.0)),
                    step(50, s1=sensor(pm=16.0, voc=210.0)),
                    step(80),
                    step(110),
                    step(230),
                ]
            )
        )

        z0 = zone(result, 0, 1)
        self.assertEqual(z0["air_quality_level"], "NORMAL")
        self.assertEqual(z0["final_supply_pct"], 30.0)
        self.assertEqual(z0["final_extract_pct"], 35.0)

        z1 = zone(result, 1, 1)
        self.assertEqual(z1["raw_air_quality_level"], "BOOST")
        self.assertEqual(z1["raw_air_quality_driver"], "PM2_5")
        self.assertEqual(z1["air_quality_level"], "NORMAL")
        self.assertEqual(z1["dynamics_pending_level"], "BOOST")
        self.assertEqual(z1["dynamics_transition_reason"], "ESCALATION_CONFIRMING")

        z2 = zone(result, 2, 1)
        self.assertEqual(z2["air_quality_level"], "NORMAL")
        self.assertEqual(z2["dynamics_transition_reason"], "ESCALATION_CONFIRMING")

        z3 = zone(result, 3, 1)
        self.assertEqual(z3["air_quality_level"], "BOOST")
        self.assertEqual(z3["dynamics_transition_reason"], "ESCALATION_CONFIRMED")
        self.assertEqual(z3["final_supply_pct"], 40.0)
        self.assertEqual(z3["final_extract_pct"], 45.0)

        z4 = zone(result, 4, 1)
        self.assertEqual(z4["air_quality_level"], "HIGH")
        self.assertEqual(z4["air_quality_driver"], "VOC")
        self.assertEqual(z4["dynamics_transition_reason"], "ESCALATED_IMMEDIATELY")
        self.assertEqual(z4["final_supply_pct"], 70.0)
        self.assertEqual(z4["final_extract_pct"], 75.0)

        z5 = zone(result, 5, 1)
        self.assertEqual(z5["air_quality_level"], "HIGH")
        self.assertEqual(z5["dynamics_transition_reason"], "MINIMUM_HOLD")

        z6 = zone(result, 6, 1)
        self.assertEqual(z6["air_quality_level"], "HIGH")
        self.assertEqual(z6["dynamics_transition_reason"], "DEESCALATION_DECAY")
        self.assertEqual(z6["dynamics_pending_level"], "NORMAL")

        z7 = zone(result, 7, 1)
        self.assertEqual(z7["air_quality_level"], "NORMAL")
        self.assertEqual(z7["dynamics_transition_reason"], "DEESCALATION_CONFIRMED")

    def test_temperature_cap_applies_only_for_good_air(self):
        result = ControlEngineScenarioRunner().run(
            scenario(
                [
                    step(
                        0,
                        cal=calendar(supply=50.0, extract=50.0),
                        s1=sensor(temp=17.0),
                    ),
                    step(
                        1,
                        cal=calendar(supply=50.0, extract=50.0),
                        s1=sensor(temp=17.0, voc=210.0),
                    ),
                ]
            )
        )

        cold_normal = zone(result, 0, 1)
        self.assertEqual(cold_normal["thermal_band"], "MINIMUM")
        self.assertEqual(cold_normal["automation_state"], "TEMP_LIMIT")
        self.assertEqual(cold_normal["temperature_limit_pct"], 30.0)
        self.assertEqual(cold_normal["final_supply_pct"], 30.0)
        self.assertEqual(cold_normal["final_extract_pct"], 35.0)
        self.assertFalse(cold_normal["air_quality_override"])

        cold_high = zone(result, 1, 1)
        self.assertEqual(cold_high["air_quality_level"], "HIGH")
        self.assertEqual(cold_high["thermal_band"], "MINIMUM")
        self.assertTrue(cold_high["air_quality_override"])
        self.assertEqual(cold_high["final_supply_pct"], 70.0)
        self.assertEqual(cold_high["final_extract_pct"], 75.0)
        self.assertEqual(cold_high["control_reason"], "LOW_TEMPERATURE + AIR_QUALITY_OVERRIDE")

    def test_sensor_loss_fallback_is_active_only_during_active_lifecycle(self):
        result = ControlEngineScenarioRunner().run(
            scenario(
                [
                    step(0, s1=sensor(usable=False)),
                    step(
                        1,
                        s1=sensor(usable=False),
                        cal=calendar(phase="INACTIVE", mode="STANDBY", supply=0.0, extract=0.0),
                    ),
                    step(2, s2=sensor(usable=False)),
                ]
            )
        )

        fan_active = zone(result, 0, 1)
        self.assertEqual(fan_active["automation_state"], "FAULT")
        self.assertTrue(fan_active["sensor_fallback_applied"])
        self.assertEqual(fan_active["final_supply_pct"], 45.0)
        self.assertEqual(fan_active["final_extract_pct"], 50.0)
        self.assertEqual(fan_active["control_reason"], "SENSOR_CONTEXT_UNAVAILABLE:FALLBACK")

        fan_inactive = zone(result, 1, 1)
        self.assertEqual(fan_inactive["automation_state"], "FAULT")
        self.assertFalse(fan_inactive["sensor_fallback_applied"])
        self.assertEqual(fan_inactive["final_supply_pct"], 0.0)
        self.assertEqual(fan_inactive["final_extract_pct"], 0.0)

        aero_active = zone(result, 2, 2)
        self.assertEqual(aero_active["automation_state"], "FAULT")
        self.assertTrue(aero_active["sensor_fallback_applied"])
        self.assertEqual(aero_active["proposed_aero_speed"], 2)

    def test_critical_safety_fault_blocks_all_shadow_requests(self):
        result = ControlEngineScenarioRunner().run(
            scenario([step(0, s1=sensor(voc=350.0), critical_alarm=True)])
        )
        payload = result.to_dict()["steps"][0]["shadow"]
        self.assertEqual(payload["status"], "BLOCKED_SAFETY")
        for row in payload["zones"]:
            self.assertTrue(row["safety_override"])
            self.assertEqual(row["automation_state"], "FAULT")
            self.assertIsNone(row["final_supply_pct"])
            self.assertIsNone(row["final_extract_pct"])
            self.assertIsNone(row["proposed_supply_voltage"])
            self.assertIsNone(row["proposed_extract_voltage"])
            self.assertIsNone(row["proposed_aero_speed"])

    def test_zigbee_freshness_is_replayed_without_affecting_actuation_authority(self):
        result = ControlEngineScenarioRunner().run(
            scenario(
                [
                    step(0, zigbee_supply={"temperature_celsius": 10.0, "age_seconds": 60.0, "available": True, "timestamp_available": True}),
                    step(1, zigbee_supply={"temperature_celsius": 10.0, "age_seconds": 20000.0, "available": True, "timestamp_available": True}),
                    step(2, zigbee_supply={"temperature_celsius": 10.0, "age_seconds": 0.0, "available": True, "timestamp_available": False}),
                ]
            )
        )

        fresh = zone(result, 0, 1)
        self.assertTrue(fresh["outside_temperature_usable"])
        self.assertEqual(fresh["outside_temperature_reason"], "OK")
        self.assertEqual(fresh["temperature_delta_celsius"], 12.0)

        stale = zone(result, 1, 1)
        self.assertFalse(stale["outside_temperature_usable"])
        self.assertTrue(stale["outside_temperature_stale"])
        self.assertEqual(stale["outside_temperature_reason"], "TEMPERATURE_STALE")
        self.assertIsNone(stale["temperature_delta_celsius"])

        no_ts = zone(result, 2, 1)
        self.assertFalse(no_ts["outside_temperature_usable"])
        self.assertEqual(no_ts["outside_temperature_reason"], "TEMPERATURE_TIMESTAMP_UNAVAILABLE")
        self.assertIsNone(no_ts["temperature_delta_celsius"])

        full = result.to_dict()
        self.assertFalse(full["actuation_supported"])
        for item in full["steps"]:
            self.assertFalse(item["shadow"]["actuation_supported"])
            for row in item["shadow"]["zones"]:
                self.assertIsNone(row["proposed_supply_voltage"])
                self.assertIsNone(row["proposed_extract_voltage"])

    def test_contract_rejects_unknown_fields_type_coercion_and_time_reversal(self):
        base = scenario([step(0)])
        bad_unknown = dict(base)
        bad_unknown["enable_actuation"] = True
        with self.assertRaises(ValueError):
            ControlEngineScenarioRunner().run(bad_unknown)

        bad_type = scenario([step(0)])
        bad_type["steps"][0]["at_seconds"] = "0"
        with self.assertRaises(ValueError):
            ControlEngineScenarioRunner().run(bad_type)

        backward = scenario([step(10), step(9)])
        with self.assertRaises(ValueError):
            ControlEngineScenarioRunner().run(backward)


if __name__ == "__main__":
    unittest.main()
