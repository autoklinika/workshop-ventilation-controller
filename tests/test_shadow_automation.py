from __future__ import annotations

import unittest

from ventilation_core.application.shadow_controller import UnconfiguredShadowAutomationEvaluator
from ventilation_core.domain.models import (
    AlarmCode,
    AlarmSeverity,
    AlarmState,
    CoreState,
    FanSetpoints,
    VentilationMode,
)
from ventilation_core.domain.schedule import (
    ScheduleExpectation,
    ScheduleState,
    ZoneScheduleState,
)
from ventilation_core.domain.sensors import AirQualityReading, SensorBusState, SensorNodeState
from ventilation_core.domain.shadow import ShadowAutomationStatus


class ShadowAutomationTest(unittest.TestCase):
    def _state(
        self,
        *,
        hardware_ready: bool = True,
        output_state_known: bool = True,
        alarms=(),
        schedule_available: bool = True,
        sensor_1_usable: bool = True,
        sensor_2_usable: bool = True,
    ) -> CoreState:
        schedule = ScheduleState(
            available=schedule_available,
            timezone="Europe/Warsaw",
            evaluated_at_utc="2026-08-17T16:00:00+00:00",
            local_time="2026-08-17T18:00:00+02:00",
            zones=(
                ZoneScheduleState(
                    zone="zone-1",
                    expectation=(
                        ScheduleExpectation.OCCUPIED_EXPECTED
                        if schedule_available
                        else ScheduleExpectation.UNKNOWN
                    ),
                ),
                ZoneScheduleState(
                    zone="zone-2",
                    expectation=(
                        ScheduleExpectation.UNOCCUPIED_EXPECTED
                        if schedule_available
                        else ScheduleExpectation.UNKNOWN
                    ),
                ),
            ),
            last_error="" if schedule_available else "db unavailable",
        )
        nodes = (
            SensorNodeState(
                slave_address=1,
                online=sensor_1_usable,
                usable=sensor_1_usable,
                measurement_valid=sensor_1_usable,
                measurement_stale=not sensor_1_usable,
                sensor_present=True,
                reading=AirQualityReading(pm2_5_ug_m3=4.0, voc_index=102.0),
            ),
            SensorNodeState(
                slave_address=2,
                online=sensor_2_usable,
                usable=sensor_2_usable,
                measurement_valid=sensor_2_usable,
                measurement_stale=not sensor_2_usable,
                sensor_present=True,
                reading=AirQualityReading(pm2_5_ug_m3=6.0, voc_index=98.0),
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
            active_alarms=tuple(alarms),
            sensor_bus=sensor_bus,
            schedule=schedule,
        )

    def test_unconfigured_policy_publishes_context_but_no_proposed_outputs(self):
        result = UnconfiguredShadowAutomationEvaluator().evaluate(self._state())

        self.assertTrue(result.enabled)
        self.assertFalse(result.actuation_supported)
        self.assertEqual(result.status, ShadowAutomationStatus.POLICY_UNCONFIGURED)
        self.assertIsNone(result.policy_version)
        self.assertEqual(len(result.zones), 2)

        zone1, zone2 = result.zones
        self.assertEqual(zone1.schedule_expectation, "OCCUPIED_EXPECTED")
        self.assertEqual(zone2.schedule_expectation, "UNOCCUPIED_EXPECTED")
        self.assertTrue(zone1.sensor_usable)
        self.assertTrue(zone2.sensor_usable)
        for proposal in result.zones:
            self.assertIsNone(proposal.air_request_pct)
            self.assertIsNone(proposal.temperature_limit_pct)
            self.assertIsNone(proposal.proposed_supply_voltage)
            self.assertIsNone(proposal.proposed_extract_voltage)
            self.assertIsNone(proposal.proposed_aero_speed)
            self.assertEqual(proposal.control_reason, "POLICY_NOT_CONFIGURED")

    def test_critical_system_alarm_blocks_shadow(self):
        alarm = AlarmState(
            code=AlarmCode.DAC_COMMUNICATION_LOST,
            severity=AlarmSeverity.CRITICAL,
            message="DAC unavailable",
            active_since="2026-08-17T16:00:00+00:00",
            last_error="timeout",
            occurrences=3,
        )
        result = UnconfiguredShadowAutomationEvaluator().evaluate(
            self._state(alarms=(alarm,))
        )

        self.assertEqual(result.status, ShadowAutomationStatus.BLOCKED_SAFETY)
        self.assertTrue(all(zone.safety_override for zone in result.zones))
        self.assertTrue(all(zone.control_reason == "SAFETY_BLOCK_ACTIVE" for zone in result.zones))

    def test_unknown_output_state_blocks_shadow_even_without_alarm(self):
        result = UnconfiguredShadowAutomationEvaluator().evaluate(
            self._state(output_state_known=False)
        )
        self.assertEqual(result.status, ShadowAutomationStatus.BLOCKED_SAFETY)
        self.assertTrue(all(zone.safety_override for zone in result.zones))

    def test_missing_sensor_context_is_explicit_and_never_invents_output(self):
        result = UnconfiguredShadowAutomationEvaluator().evaluate(
            self._state(sensor_1_usable=False)
        )
        zone1 = result.zones[0]
        self.assertFalse(zone1.sensor_usable)
        self.assertEqual(zone1.control_reason, "SENSOR_CONTEXT_UNAVAILABLE")
        self.assertIsNone(zone1.proposed_supply_voltage)
        self.assertIsNone(zone1.proposed_extract_voltage)

    def test_corestate_serializes_forward_compatible_shadow_contract(self):
        state = self._state()
        shadow = UnconfiguredShadowAutomationEvaluator().evaluate(state)
        state = CoreState(
            mode=state.mode,
            setpoints=state.setpoints,
            hardware_ready=state.hardware_ready,
            output_state_known=state.output_state_known,
            active_alarms=state.active_alarms,
            sensor_bus=state.sensor_bus,
            schedule=state.schedule,
            shadow_automation=shadow,
        )

        payload = state.to_dict()
        self.assertEqual(payload["setpoints"], {"supply_voltage": 0.0, "extract_voltage": 0.0})
        self.assertEqual(payload["shadow_automation"]["status"], "POLICY_UNCONFIGURED")
        self.assertFalse(payload["shadow_automation"]["actuation_supported"])
        self.assertIsNone(payload["shadow_automation"]["zones"][0]["proposed_supply_voltage"])


if __name__ == "__main__":
    unittest.main()
