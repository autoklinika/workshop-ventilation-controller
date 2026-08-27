from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.application.zigbee_measurements import DEFAULT_ZIGBEE_STALE_SECONDS
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.sensors import AirQualityReading, SensorBusState, SensorNodeState
from ventilation_core.domain.shadow import ShadowAutomationStatus
from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1
from ventilation_core.domain.zigbee import ZigbeeMqttState, ZigbeeTemperatureSensorState


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def policy() -> ShadowPolicyV1:
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


def zigbee(*, supply_age: float = 60.0, supply_temp: float = 5.0, supply_available: bool | None = True) -> ZigbeeMqttState:
    supply_seen = (NOW - timedelta(seconds=supply_age)).isoformat()
    extract_seen = (NOW - timedelta(seconds=90)).isoformat()
    return ZigbeeMqttState(
        broker_host="127.0.0.1",
        broker_port=1883,
        base_topic="zigbee2mqtt",
        running=True,
        connected=True,
        bridge_online=True,
        devices=(
            ZigbeeTemperatureSensorState(
                role="supply",
                friendly_name="temp_nawiew",
                ieee_address="0xsupply",
                topic="zigbee2mqtt/temp_nawiew",
                available=supply_available,
                temperature_celsius=supply_temp,
                last_seen=supply_seen,
                last_message_at=supply_seen,
                messages=1,
            ),
            ZigbeeTemperatureSensorState(
                role="extract",
                friendly_name="temp_wywiew",
                ieee_address="0xextract",
                topic="zigbee2mqtt/temp_wywiew",
                available=True,
                temperature_celsius=18.0,
                last_seen=extract_seen,
                last_message_at=extract_seen,
                messages=1,
            ),
        ),
    )


def state(zigbee_state: ZigbeeMqttState | None) -> CoreState:
    reading1 = AirQualityReading(
        pm2_5_ug_m3=5.0,
        pm10_0_ug_m3=10.0,
        voc_index=100.0,
        nox_index=5.0,
        temperature_celsius=21.0,
    )
    reading2 = AirQualityReading(
        pm2_5_ug_m3=5.0,
        pm10_0_ug_m3=10.0,
        voc_index=100.0,
        nox_index=5.0,
        temperature_celsius=22.0,
    )
    nodes = tuple(
        SensorNodeState(
            slave_address=address,
            online=True,
            usable=True,
            measurement_valid=True,
            measurement_stale=False,
            sensor_present=True,
            reading=reading,
        )
        for address, reading in ((1, reading1), (2, reading2))
    )
    calendar = CalendarResolution(
        available=True,
        timezone="Europe/Warsaw",
        evaluated_at_utc=NOW.isoformat(),
        local_time="2026-08-27T14:00:00+02:00",
        phase=CalendarPhase.ACTIVE,
        effective_profile="WORK",
        effective_mode=CalendarMode.AUTO,
        rule_id="THURSDAY",
        schedule_supply_pct=40.0,
        schedule_extract_pct=45.0,
        schedule_request_source="CALENDAR_AUTO_MINIMUM",
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
        zigbee=zigbee_state,
        calendar=calendar,
    )


class ControlEngineZigbeeTemperatureTest(unittest.TestCase):
    def evaluate(self, zigbee_state: ZigbeeMqttState | None):
        evaluator = PolicyShadowAutomationEvaluator(policy(), clock=lambda: NOW)
        result = evaluator.evaluate(state(zigbee_state))
        self.assertFalse(result.actuation_supported)
        return result

    def test_fresh_supply_role_populates_outside_temperature_and_delta(self) -> None:
        result = self.evaluate(zigbee())
        self.assertEqual(result.status, ShadowAutomationStatus.READY)
        zone1 = result.zones[0]
        self.assertEqual(zone1.outside_temperature_celsius, 5.0)
        self.assertTrue(zone1.outside_temperature_usable)
        self.assertFalse(zone1.outside_temperature_stale)
        self.assertAlmostEqual(zone1.outside_temperature_age_seconds or 0.0, 60.0)
        self.assertEqual(zone1.outside_temperature_source, "zigbee:supply")
        self.assertEqual(zone1.outside_temperature_reason, "OK")
        self.assertEqual(zone1.temperature_delta_celsius, 16.0)
        # Supply-air context is telemetry-only in this stage.
        self.assertEqual(zone1.final_supply_pct, 40.0)
        self.assertEqual(zone1.final_extract_pct, 45.0)
        self.assertIsNone(zone1.proposed_supply_voltage)
        self.assertIsNone(zone1.proposed_extract_voltage)

    def test_stale_supply_temperature_is_visible_but_delta_is_suppressed(self) -> None:
        result = self.evaluate(
            zigbee(supply_age=DEFAULT_ZIGBEE_STALE_SECONDS + 1)
        )
        zone1 = result.zones[0]
        self.assertEqual(zone1.outside_temperature_celsius, 5.0)
        self.assertFalse(zone1.outside_temperature_usable)
        self.assertTrue(zone1.outside_temperature_stale)
        self.assertEqual(zone1.outside_temperature_reason, "TEMPERATURE_STALE")
        self.assertIsNone(zone1.temperature_delta_celsius)
        # Not yet a control dependency, therefore no degradation of the engine.
        self.assertEqual(result.status, ShadowAutomationStatus.READY)
        self.assertEqual(zone1.final_supply_pct, 40.0)

    def test_missing_zigbee_is_explicit_but_not_yet_a_control_failure(self) -> None:
        result = self.evaluate(None)
        zone1 = result.zones[0]
        self.assertIsNone(zone1.outside_temperature_celsius)
        self.assertFalse(zone1.outside_temperature_usable)
        self.assertEqual(zone1.outside_temperature_reason, "ZIGBEE_STATE_UNAVAILABLE")
        self.assertIsNone(zone1.temperature_delta_celsius)
        self.assertEqual(result.status, ShadowAutomationStatus.READY)

    def test_extract_role_is_not_used_as_outdoor_temperature(self) -> None:
        result = self.evaluate(zigbee())
        zone1, zone2 = result.zones
        self.assertEqual(zone1.outside_temperature_celsius, 5.0)
        self.assertNotEqual(zone1.outside_temperature_celsius, 18.0)
        self.assertIsNone(zone2.outside_temperature_celsius)
        self.assertEqual(zone2.outside_temperature_reason, "NOT_APPLICABLE")


if __name__ == "__main__":
    unittest.main()
