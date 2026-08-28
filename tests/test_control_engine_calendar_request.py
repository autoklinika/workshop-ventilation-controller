from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.calendar import (
    CalendarConfig,
    CalendarMode,
    CalendarProfile,
    CalendarRule,
    CalendarRuleKind,
    resolve_calendar,
)
from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.sensors import AirQualityReading, SensorBusState, SensorNodeState
from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1


def tuned_policy() -> ShadowPolicyV1:
    return ShadowPolicyV1(
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
        )
    )


def calendar_config(*, mode: CalendarMode = CalendarMode.AUTO) -> CalendarConfig:
    if mode == CalendarMode.AUTO:
        profile = CalendarProfile(
            "WORK",
            CalendarMode.AUTO,
            minimum_supply_pct=40.0,
            minimum_extract_pct=45.0,
        )
    elif mode == CalendarMode.FIXED:
        profile = CalendarProfile(
            "WORK",
            CalendarMode.FIXED,
            fixed_supply_pct=35.0,
            fixed_extract_pct=40.0,
        )
    else:
        profile = CalendarProfile("WORK", mode)
    return CalendarConfig(
        timezone="Europe/Warsaw",
        profiles=(profile, CalendarProfile("CLOSED", CalendarMode.STANDBY)),
        rules=(
            CalendarRule("default", CalendarRuleKind.DEFAULT, "CLOSED"),
            CalendarRule(
                "thursday",
                CalendarRuleKind.WEEKLY,
                "WORK",
                weekdays=(4,),
                start_minute=7 * 60,
                end_minute=17 * 60,
            ),
        ),
    )


def core_state(calendar, *, pm: float = 10.0, temp: float = 21.0) -> CoreState:
    nodes = (
        SensorNodeState(
            slave_address=1,
            online=True,
            usable=True,
            measurement_valid=True,
            measurement_stale=False,
            sensor_present=True,
            reading=AirQualityReading(
                pm2_5_ug_m3=pm,
                pm10_0_ug_m3=20.0,
                voc_index=100.0,
                nox_index=5.0,
                temperature_celsius=temp,
            ),
        ),
        SensorNodeState(
            slave_address=2,
            online=True,
            usable=True,
            measurement_valid=True,
            measurement_stale=False,
            sensor_present=True,
            reading=AirQualityReading(
                pm2_5_ug_m3=5.0,
                pm10_0_ug_m3=10.0,
                voc_index=100.0,
                nox_index=5.0,
                temperature_celsius=21.0,
            ),
        ),
    )
    return CoreState(
        mode=VentilationMode.STOP,
        setpoints=FanSetpoints.stopped(),
        hardware_ready=True,
        output_state_known=True,
        sensor_bus=SensorBusState(
            port="/dev/ttyAMA0",
            baudrate=19200,
            addresses=(1, 2),
            ready=True,
            worker_alive=True,
            nodes=nodes,
        ),
        calendar=calendar,
    )


class CalendarControlIntentTest(unittest.TestCase):
    def test_auto_profile_exposes_minimum_request(self) -> None:
        state = resolve_calendar(
            calendar_config(mode=CalendarMode.AUTO),
            now_utc=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(state.effective_mode, CalendarMode.AUTO)
        self.assertEqual(state.schedule_supply_pct, 40.0)
        self.assertEqual(state.schedule_extract_pct, 45.0)
        self.assertEqual(state.schedule_request_source, "CALENDAR_AUTO_MINIMUM")
        payload = state.to_dict()
        self.assertEqual(payload["schedule_supply_pct"], 40.0)
        self.assertEqual(payload["schedule_extract_pct"], 45.0)

    def test_fixed_profile_exposes_fixed_request(self) -> None:
        state = resolve_calendar(
            calendar_config(mode=CalendarMode.FIXED),
            now_utc=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(state.schedule_supply_pct, 35.0)
        self.assertEqual(state.schedule_extract_pct, 40.0)
        self.assertEqual(state.schedule_request_source, "CALENDAR_FIXED")

    def test_inactive_default_standby_exposes_zero_baseline(self) -> None:
        state = resolve_calendar(
            calendar_config(mode=CalendarMode.AUTO),
            now_utc=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(state.effective_mode, CalendarMode.STANDBY)
        self.assertEqual(state.schedule_supply_pct, 0.0)
        self.assertEqual(state.schedule_extract_pct, 0.0)
        self.assertEqual(state.schedule_request_source, "CALENDAR_STANDBY")


class ControlEngineCalendarCombinationTest(unittest.TestCase):
    def evaluate(self, calendar, *, pm: float = 10.0, temp: float = 21.0):
        evaluator = PolicyShadowAutomationEvaluator(
            tuned_policy(),
            clock=lambda: datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        )
        result = evaluator.evaluate(core_state(calendar, pm=pm, temp=temp))
        self.assertFalse(result.actuation_supported)
        return result.zones[0]

    def test_active_good_air_uses_max_of_calendar_and_normal_air_request(self) -> None:
        calendar = resolve_calendar(
            calendar_config(mode=CalendarMode.AUTO),
            now_utc=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        )
        zone = self.evaluate(calendar)
        self.assertEqual(zone.schedule_supply_pct, 40.0)
        self.assertEqual(zone.schedule_extract_pct, 45.0)
        self.assertEqual(zone.final_supply_pct, 40.0)
        self.assertEqual(zone.final_extract_pct, 45.0)
        self.assertIsNone(zone.proposed_supply_voltage)
        self.assertIsNone(zone.proposed_extract_voltage)

    def test_temperature_caps_only_good_air_baseline(self) -> None:
        calendar = resolve_calendar(
            calendar_config(mode=CalendarMode.AUTO),
            now_utc=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        )
        zone = self.evaluate(calendar, temp=17.0)
        self.assertEqual(zone.thermal_band, "MINIMUM")
        self.assertEqual(zone.temperature_limit_pct, 30.0)
        self.assertEqual(zone.final_supply_pct, 30.0)
        self.assertEqual(zone.final_extract_pct, 35.0)

    def test_standby_good_air_does_not_invent_background_ventilation(self) -> None:
        calendar = resolve_calendar(
            calendar_config(mode=CalendarMode.AUTO),
            now_utc=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
        )
        zone = self.evaluate(calendar)
        self.assertEqual(zone.automation_state, "STANDBY")
        self.assertEqual(zone.air_quality_level, "NORMAL")
        self.assertEqual(zone.final_supply_pct, 0.0)
        self.assertEqual(zone.final_extract_pct, 0.0)

    def test_degraded_air_overrides_standby_and_temperature_limit(self) -> None:
        calendar = resolve_calendar(
            calendar_config(mode=CalendarMode.AUTO),
            now_utc=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
        )
        zone = self.evaluate(calendar, pm=30.0, temp=17.0)
        self.assertEqual(zone.automation_state, "BOOST")
        self.assertEqual(zone.air_quality_level, "HIGH")
        self.assertTrue(zone.air_quality_override)
        self.assertEqual(zone.final_supply_pct, 75.0)
        self.assertEqual(zone.final_extract_pct, 80.0)


if __name__ == "__main__":
    unittest.main()
