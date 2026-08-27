from __future__ import annotations

import unittest
from datetime import datetime, timezone

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


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def tuning(*, fallback: bool = True) -> ShadowOutputTuning:
    return ShadowOutputTuning(
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
        sensor_fallback_supply_pct=55.0 if fallback else None,
        sensor_fallback_extract_pct=60.0 if fallback else None,
        aero_sensor_fallback_speed=2 if fallback else None,
    )


def node(address: int, *, usable: bool, stale: bool = False) -> SensorNodeState:
    return SensorNodeState(
        slave_address=address,
        online=usable,
        usable=usable,
        measurement_valid=usable,
        measurement_stale=stale,
        sensor_present=usable,
        # Deliberately dangerous values ensure an unusable/stale reading is not
        # accidentally consumed as live air-quality data.
        reading=AirQualityReading(
            pm2_5_ug_m3=100.0,
            pm10_0_ug_m3=100.0,
            voc_index=400.0,
            nox_index=200.0,
            temperature_celsius=10.0,
        ),
    )


def state(
    *,
    phase: CalendarPhase = CalendarPhase.ACTIVE,
    mode: CalendarMode = CalendarMode.AUTO,
    zone1_usable: bool = False,
    zone2_usable: bool = False,
    alarms: tuple[AlarmState, ...] = (),
) -> CoreState:
    calendar = CalendarResolution(
        available=True,
        timezone="Europe/Warsaw",
        evaluated_at_utc=NOW.isoformat(),
        local_time="2026-08-27T14:00:00+02:00",
        phase=phase,
        effective_profile="WORK" if phase != CalendarPhase.INACTIVE else "CLOSED",
        effective_mode=mode,
        rule_id="TEST",
        schedule_supply_pct=40.0 if phase != CalendarPhase.INACTIVE else 0.0,
        schedule_extract_pct=45.0 if phase != CalendarPhase.INACTIVE else 0.0,
        schedule_request_source=(
            "CALENDAR_AUTO_MINIMUM" if phase != CalendarPhase.INACTIVE else "CALENDAR_STANDBY"
        ),
    )
    return CoreState(
        mode=VentilationMode.STOP,
        setpoints=FanSetpoints.stopped(),
        hardware_ready=True,
        output_state_known=True,
        active_alarms=alarms,
        sensor_bus=SensorBusState(
            port="/dev/ttyAMA0",
            baudrate=19200,
            addresses=(1, 2),
            ready=zone1_usable and zone2_usable,
            worker_alive=True,
            nodes=(
                node(1, usable=zone1_usable, stale=not zone1_usable),
                node(2, usable=zone2_usable, stale=not zone2_usable),
            ),
        ),
        calendar=calendar,
    )


class ControlEngineSensorFallbackTest(unittest.TestCase):
    def evaluator(self, *, fallback: bool = True) -> PolicyShadowAutomationEvaluator:
        return PolicyShadowAutomationEvaluator(
            ShadowPolicyV1(tuning=tuning(fallback=fallback)),
            clock=lambda: NOW,
        )

    def test_active_fan_zone_uses_explicit_fallback_and_not_stale_reading(self) -> None:
        result = self.evaluator().evaluate(
            state(zone1_usable=False, zone2_usable=True)
        )
        self.assertEqual(result.status, ShadowAutomationStatus.DEGRADED)
        zone = result.zones[0]
        self.assertEqual(zone.automation_state, "FAULT")
        self.assertFalse(zone.sensor_usable)
        self.assertTrue(zone.sensor_fallback_applied)
        self.assertEqual(zone.final_supply_pct, 55.0)
        self.assertEqual(zone.final_extract_pct, 60.0)
        self.assertEqual(zone.control_reason, "SENSOR_CONTEXT_UNAVAILABLE:FALLBACK")
        self.assertIsNone(zone.raw_air_quality_level)
        self.assertIsNone(zone.air_quality_level)
        self.assertIsNone(zone.inside_temperature_celsius)
        self.assertIsNone(zone.proposed_supply_voltage)
        self.assertIsNone(zone.proposed_extract_voltage)

    def test_calendar_baseline_remains_a_floor_for_fallback(self) -> None:
        custom = tuning(fallback=True)
        custom = ShadowOutputTuning(
            **{
                **custom.__dict__,
                "sensor_fallback_supply_pct": 25.0,
                "sensor_fallback_extract_pct": 30.0,
            }
        )
        evaluator = PolicyShadowAutomationEvaluator(
            ShadowPolicyV1(tuning=custom),
            clock=lambda: NOW,
        )
        zone = evaluator.evaluate(
            state(zone1_usable=False, zone2_usable=True)
        ).zones[0]
        self.assertEqual(zone.final_supply_pct, 40.0)
        self.assertEqual(zone.final_extract_pct, 45.0)
        self.assertTrue(zone.sensor_fallback_applied)

    def test_active_aero_zone_uses_explicit_speed_fallback(self) -> None:
        result = self.evaluator().evaluate(
            state(zone1_usable=True, zone2_usable=False)
        )
        zone = result.zones[1]
        self.assertEqual(zone.automation_state, "FAULT")
        self.assertTrue(zone.sensor_fallback_applied)
        self.assertEqual(zone.proposed_aero_speed, 2)
        self.assertEqual(zone.control_reason, "SENSOR_CONTEXT_UNAVAILABLE:FALLBACK")
        self.assertFalse(result.actuation_supported)

    def test_missing_fallback_tuning_is_explicit_and_does_not_invent_output(self) -> None:
        result = self.evaluator(fallback=False).evaluate(
            state(zone1_usable=False, zone2_usable=True)
        )
        zone = result.zones[0]
        self.assertFalse(zone.sensor_fallback_applied)
        self.assertIsNone(zone.final_supply_pct)
        self.assertIsNone(zone.final_extract_pct)
        self.assertEqual(
            zone.control_reason,
            "SENSOR_CONTEXT_UNAVAILABLE:FALLBACK_TUNING_REQUIRED",
        )

    def test_inactive_sensor_loss_does_not_invent_background_ventilation(self) -> None:
        result = self.evaluator().evaluate(
            state(
                phase=CalendarPhase.INACTIVE,
                mode=CalendarMode.STANDBY,
                zone1_usable=False,
                zone2_usable=False,
            )
        )
        zone1, zone2 = result.zones
        self.assertEqual(zone1.final_supply_pct, 0.0)
        self.assertEqual(zone1.final_extract_pct, 0.0)
        self.assertFalse(zone1.sensor_fallback_applied)
        self.assertEqual(zone1.control_reason, "SENSOR_CONTEXT_UNAVAILABLE:INACTIVE")
        self.assertEqual(zone2.proposed_aero_speed, 0)
        self.assertFalse(zone2.sensor_fallback_applied)

    def test_critical_safety_block_has_priority_over_sensor_fallback(self) -> None:
        alarm = AlarmState(
            code=AlarmCode.DAC_COMMUNICATION_LOST,
            severity=AlarmSeverity.CRITICAL,
            message="DAC unavailable",
            active_since=NOW.isoformat(),
            last_error="timeout",
            occurrences=1,
        )
        result = self.evaluator().evaluate(
            state(
                zone1_usable=False,
                zone2_usable=False,
                alarms=(alarm,),
            )
        )
        self.assertEqual(result.status, ShadowAutomationStatus.BLOCKED_SAFETY)
        for zone in result.zones:
            self.assertFalse(zone.sensor_fallback_applied)
            self.assertIsNone(zone.final_supply_pct)
            self.assertIsNone(zone.final_extract_pct)
            self.assertIsNone(zone.proposed_aero_speed)
            self.assertEqual(zone.control_reason, "SAFETY_BLOCK_ACTIVE")

    def test_partial_fan_fallback_configuration_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires both"):
            ShadowOutputTuning(sensor_fallback_supply_pct=50.0)


if __name__ == "__main__":
    unittest.main()
