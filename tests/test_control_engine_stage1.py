from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.domain.models import (
    AlarmCode,
    AlarmSeverity,
    AlarmState,
    CoreState,
    FanSetpoints,
    VentilationMode,
)
from ventilation_core.domain.sensors import AirQualityReading, SensorBusState, SensorNodeState
from ventilation_core.domain.shadow import ShadowAutomationStatus
from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def tuned_policy() -> ShadowPolicyV1:
    return ShadowPolicyV1(
        version="control-engine-v1-stage1-test",
        tuning=ShadowOutputTuning(
            normal_air_request_pct=30.0,
            boost_air_request_pct=50.0,
            high_air_request_pct=75.0,
            max_air_request_pct=100.0,
            thermal_normal_limit_pct=100.0,
            thermal_limiting_limit_pct=60.0,
            thermal_minimum_limit_pct=30.0,
            thermal_protection_limit_pct=15.0,
            extract_bias_pct=5.0,
            aero_normal_speed=1,
            aero_boost_speed=2,
            aero_high_speed=3,
            aero_max_speed=3,
            pm2_5_hysteresis_ug_m3=2.0,
            voc_hysteresis_index=10.0,
            nox_hysteresis_index=5.0,
            temperature_hysteresis_celsius=0.5,
            pm2_5_boost_confirmation_seconds=60.0,
            state_minimum_hold_seconds=120.0,
            boost_decay_seconds=180.0,
        ),
    )


def core_state(
    zone1: AirQualityReading,
    *,
    zone2: AirQualityReading | None = None,
    phase: CalendarPhase = CalendarPhase.ACTIVE,
    mode: CalendarMode = CalendarMode.AUTO,
    alarms: tuple[AlarmState, ...] = (),
    hardware_ready: bool = True,
    output_state_known: bool = True,
) -> CoreState:
    zone2 = zone2 or AirQualityReading(
        pm2_5_ug_m3=5.0,
        pm10_0_ug_m3=10.0,
        voc_index=100.0,
        nox_index=5.0,
        temperature_celsius=21.0,
    )
    calendar = CalendarResolution(
        available=True,
        timezone="Europe/Warsaw",
        evaluated_at_utc="2026-08-27T12:00:00+00:00",
        local_time="2026-08-27T14:00:00+02:00",
        phase=phase,
        effective_profile="NORMAL_WORKDAY",
        effective_mode=mode,
        rule_id="MON_FRI",
    )
    nodes = (
        SensorNodeState(
            slave_address=1,
            online=True,
            usable=True,
            measurement_valid=True,
            measurement_stale=False,
            sensor_present=True,
            reading=zone1,
        ),
        SensorNodeState(
            slave_address=2,
            online=True,
            usable=True,
            measurement_valid=True,
            measurement_stale=False,
            sensor_present=True,
            reading=zone2,
        ),
    )
    sensor_bus = SensorBusState(
        port="/dev/ttyAMA0",
        baudrate=19200,
        addresses=(1, 2),
        ready=True,
        worker_alive=True,
        nodes=nodes,
    )
    return CoreState(
        mode=VentilationMode.STOP,
        setpoints=FanSetpoints.stopped(),
        hardware_ready=hardware_ready,
        output_state_known=output_state_known,
        active_alarms=alarms,
        sensor_bus=sensor_bus,
        calendar=calendar,
    )


def reading(*, pm: float = 10.0, voc: float = 100.0, nox: float = 5.0, temp: float = 21.0) -> AirQualityReading:
    return AirQualityReading(
        pm2_5_ug_m3=pm,
        pm10_0_ug_m3=20.0,
        voc_index=voc,
        nox_index=nox,
        temperature_celsius=temp,
    )


class ControlEngineStage1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()
        self.evaluator = PolicyShadowAutomationEvaluator(
            tuned_policy(),
            clock=self.clock,
        )

    def zone1(self, state: CoreState):
        result = self.evaluator.evaluate(state)
        self.assertFalse(result.actuation_supported)
        self.assertEqual(result.status, ShadowAutomationStatus.READY)
        return result.zones[0]

    def test_pm2_5_confirmation_is_visible_in_authoritative_shadow_telemetry(self) -> None:
        initial = self.zone1(core_state(reading(pm=10.0)))
        self.assertEqual(initial.automation_state, "NORMAL")
        self.assertEqual(initial.raw_air_quality_level, "NORMAL")
        self.assertEqual(initial.air_quality_level, "NORMAL")
        self.assertIsNone(initial.dynamics_pending_level)
        self.assertIsNone(initial.proposed_supply_voltage)
        self.assertIsNone(initial.proposed_extract_voltage)

        self.clock.advance(10)
        pending = self.zone1(core_state(reading(pm=20.0)))
        self.assertEqual(pending.raw_air_quality_level, "BOOST")
        self.assertEqual(pending.air_quality_level, "NORMAL")
        self.assertEqual(pending.dynamics_pending_level, "BOOST")
        self.assertEqual(pending.dynamics_pending_driver, "PM2_5")
        self.assertEqual(pending.dynamics_transition_reason, "ESCALATION_CONFIRMING")
        self.assertEqual(pending.control_reason, "AIR_QUALITY_CONFIRMING:BOOST")
        self.assertEqual(pending.automation_state, "NORMAL")
        self.assertEqual(pending.final_supply_pct, 30.0)

        self.clock.advance(60)
        confirmed = self.zone1(core_state(reading(pm=20.0)))
        self.assertEqual(confirmed.air_quality_level, "BOOST")
        self.assertEqual(confirmed.automation_state, "BOOST")
        self.assertEqual(confirmed.final_supply_pct, 50.0)
        self.assertEqual(confirmed.final_extract_pct, 55.0)
        self.assertIsNone(confirmed.proposed_supply_voltage)
        self.assertIsNone(confirmed.proposed_extract_voltage)

    def test_high_and_max_escalate_immediately(self) -> None:
        self.zone1(core_state(reading(pm=10.0)))
        self.clock.advance(1)
        high = self.zone1(core_state(reading(pm=30.0)))
        self.assertEqual(high.air_quality_level, "HIGH")
        self.assertEqual(high.automation_state, "BOOST")
        self.assertEqual(high.final_supply_pct, 75.0)

        self.clock.advance(1)
        emergency = self.zone1(core_state(reading(pm=51.0)))
        self.assertEqual(emergency.air_quality_level, "MAX")
        self.assertEqual(emergency.automation_state, "EMERGENCY_VENT")
        self.assertEqual(emergency.final_supply_pct, 100.0)

    def test_temperature_state_is_hysteretic_and_air_quality_has_priority(self) -> None:
        cold = self.zone1(core_state(reading(pm=10.0, temp=17.0)))
        self.assertEqual(cold.raw_thermal_band, "MINIMUM")
        self.assertEqual(cold.thermal_band, "MINIMUM")
        self.assertEqual(cold.automation_state, "TEMP_LIMIT")
        self.assertEqual(cold.final_supply_pct, 30.0)

        self.clock.advance(1)
        recovery_held = self.zone1(core_state(reading(pm=10.0, temp=18.2)))
        self.assertEqual(recovery_held.raw_thermal_band, "LIMITING")
        self.assertEqual(recovery_held.thermal_band, "MINIMUM")
        self.assertEqual(recovery_held.automation_state, "TEMP_LIMIT")

        self.clock.advance(1)
        high_air = self.zone1(core_state(reading(pm=30.0, temp=17.0)))
        self.assertTrue(high_air.air_quality_override)
        self.assertEqual(high_air.automation_state, "BOOST")
        self.assertEqual(high_air.final_supply_pct, 75.0)
        self.assertEqual(high_air.control_reason, "LOW_TEMPERATURE + AIR_QUALITY_OVERRIDE")

    def test_calendar_phases_map_to_explicit_automation_states(self) -> None:
        pre = self.zone1(core_state(reading(), phase=CalendarPhase.PREVENTILATION))
        self.assertEqual(pre.automation_state, "PREVENTILATION")

        self.clock.advance(1)
        purge = self.zone1(core_state(reading(), phase=CalendarPhase.PURGE))
        self.assertEqual(purge.automation_state, "PURGE")

        self.clock.advance(1)
        off = self.zone1(
            core_state(reading(), phase=CalendarPhase.INACTIVE, mode=CalendarMode.OFF)
        )
        self.assertEqual(off.automation_state, "OFF")

        self.clock.advance(1)
        standby = self.zone1(
            core_state(reading(), phase=CalendarPhase.INACTIVE, mode=CalendarMode.STANDBY)
        )
        self.assertEqual(standby.automation_state, "STANDBY")

    def test_critical_safety_state_is_fault_and_never_proposes_physical_voltage(self) -> None:
        alarm = AlarmState(
            code=AlarmCode.DAC_COMMUNICATION_LOST,
            severity=AlarmSeverity.CRITICAL,
            message="DAC unavailable",
            active_since="2026-08-27T12:00:00+00:00",
            last_error="timeout",
            occurrences=1,
        )
        result = self.evaluator.evaluate(core_state(reading(pm=51.0), alarms=(alarm,)))
        self.assertEqual(result.status, ShadowAutomationStatus.BLOCKED_SAFETY)
        zone = result.zones[0]
        self.assertEqual(zone.automation_state, "FAULT")
        self.assertTrue(zone.safety_override)
        self.assertIsNone(zone.final_supply_pct)
        self.assertIsNone(zone.final_extract_pct)
        self.assertIsNone(zone.proposed_supply_voltage)
        self.assertIsNone(zone.proposed_extract_voltage)

    def test_aero_proposal_remains_shadow_only(self) -> None:
        result = self.evaluator.evaluate(
            core_state(
                reading(),
                zone2=reading(voc=220.0),
            )
        )
        zone2 = result.zones[1]
        self.assertEqual(zone2.air_quality_level, "HIGH")
        self.assertEqual(zone2.automation_state, "BOOST")
        self.assertEqual(zone2.proposed_aero_speed, 3)
        self.assertFalse(result.actuation_supported)


if __name__ == "__main__":
    unittest.main()
