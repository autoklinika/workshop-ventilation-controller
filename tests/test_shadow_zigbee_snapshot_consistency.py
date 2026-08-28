from __future__ import annotations

import unittest

from ventilation_core.application.shadow_service import ShadowAlertingVentilationService
from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.shadow import ShadowAutomationState, ShadowAutomationStatus
from ventilation_core.domain.zigbee import ZigbeeMqttState, ZigbeeTemperatureSensorState


class _SequenceZigbeeMonitor:
    def __init__(self, states: tuple[ZigbeeMqttState, ...]) -> None:
        self._states = states
        self.calls = 0

    def state(self) -> ZigbeeMqttState:
        index = min(self.calls, len(self._states) - 1)
        self.calls += 1
        return self._states[index]


class _CapturingEvaluator:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_state: CoreState | None = None

    def evaluate(self, state: CoreState) -> ShadowAutomationState:
        self.calls += 1
        self.seen_state = state
        temperature = None
        if state.zigbee is not None and state.zigbee.devices:
            temperature = state.zigbee.devices[0].temperature_celsius
        return ShadowAutomationState(
            enabled=True,
            actuation_supported=False,
            status=ShadowAutomationStatus.TUNING_REQUIRED,
            evaluated_at_utc="2026-08-28T07:00:00+00:00",
            policy_version=f"snapshot-temperature:{temperature}",
            zones=(),
        )


class _AlertRegistryStub:
    @staticmethod
    def active_alarm_states():
        return ()


class ShadowZigbeeSnapshotConsistencyTest(unittest.TestCase):
    @staticmethod
    def _core_state() -> CoreState:
        return CoreState(
            mode=VentilationMode.STOP,
            setpoints=FanSetpoints.stopped(),
            hardware_ready=True,
            output_state_known=True,
        )

    @staticmethod
    def _zigbee_state(temperature: float) -> ZigbeeMqttState:
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
                    ieee_address="0xa4c13810e66fffff",
                    topic="zigbee2mqtt/temp_nawiew",
                    available=True,
                    temperature_celsius=temperature,
                    last_seen="2026-08-28T07:00:00+00:00",
                    last_message_at="2026-08-28T07:00:00+00:00",
                    messages=1,
                ),
            ),
        )

    def _service_without_init(self, monitor, evaluator):
        service = object.__new__(ShadowAlertingVentilationService)
        service._zigbee = monitor
        service._shadow_evaluator = evaluator
        service._system_alerts = _AlertRegistryStub()
        return service

    def test_system_alert_hook_does_not_evaluate_shadow_before_zigbee_attachment(self) -> None:
        evaluator = _CapturingEvaluator()
        monitor = _SequenceZigbeeMonitor((self._zigbee_state(20.0),))
        service = self._service_without_init(monitor, evaluator)

        result = service._with_system_alerts(self._core_state())

        self.assertEqual(evaluator.calls, 0)
        self.assertEqual(monitor.calls, 0)
        self.assertIsNone(result.zigbee)
        self.assertIsNone(result.shadow_automation)

    def test_shadow_and_corestate_use_the_exact_same_single_zigbee_snapshot(self) -> None:
        first = self._zigbee_state(20.0)
        second = self._zigbee_state(21.5)
        evaluator = _CapturingEvaluator()
        monitor = _SequenceZigbeeMonitor((first, second))
        service = self._service_without_init(monitor, evaluator)

        result = service._with_zigbee(self._core_state())

        self.assertEqual(monitor.calls, 1)
        self.assertEqual(evaluator.calls, 1)
        self.assertIsNotNone(evaluator.seen_state)
        self.assertIs(evaluator.seen_state.zigbee, result.zigbee)
        self.assertIs(result.zigbee, first)
        self.assertEqual(result.zigbee.devices[0].temperature_celsius, 20.0)
        self.assertEqual(
            result.shadow_automation.policy_version,
            "snapshot-temperature:20.0",
        )


if __name__ == "__main__":
    unittest.main()
