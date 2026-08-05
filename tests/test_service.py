import unittest

from ventilation_core.application.service import (
    HardwareFaultActiveError,
    VentilationService,
)
from ventilation_core.domain.models import AlarmCode, FanSetpoints, VentilationMode
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.domain.sensors import SensorBusState, SensorNodeState


class FakeActuator:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.last_error = None if ready else "No response from GP8403"
        self.applied = FanSetpoints.stopped()
        self.closed = False
        self.fail_health = False
        self.fail_apply = False
        self.fail_recover = False
        self.fail_close = False
        self.health_calls = 0
        self.recover_calls = 0

    def apply(self, setpoints: FanSetpoints) -> None:
        if self.fail_apply:
            self.ready = False
            self.last_error = "I2C write failed"
            raise RuntimeError(self.last_error)
        self.applied = setpoints

    def stop_all(self) -> None:
        if not self.ready:
            return
        self.applied = FanSetpoints.stopped()

    def health_check(self) -> None:
        self.health_calls += 1
        if self.fail_health:
            self.ready = False
            self.last_error = "No response from GP8403"
            raise RuntimeError(self.last_error)

    def recover(self) -> None:
        self.recover_calls += 1
        if self.fail_recover:
            self.ready = False
            self.last_error = "No response from GP8403"
            raise RuntimeError(self.last_error)
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()

    def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise RuntimeError("Actuator close failed")


class FakeSensorBus:
    def __init__(self) -> None:
        self.health_calls = 0
        self.closed = False
        self.fail_health = False
        self.current_state = SensorBusState(
            port="/dev/ttyAMA0",
            baudrate=19200,
            addresses=(1, 2),
            ready=True,
            worker_alive=True,
            nodes=(
                SensorNodeState(slave_address=1, online=True, usable=True),
                SensorNodeState(slave_address=2, online=True, usable=True),
            ),
        )

    def state(self) -> SensorBusState:
        return self.current_state

    def health_check(self) -> None:
        self.health_calls += 1
        if self.fail_health:
            raise RuntimeError("Sensor worker stopped")

    def close(self) -> None:
        self.closed = True


class VentilationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.actuator = FakeActuator()
        self.service = VentilationService(
            self.actuator,
            FanSetpointPolicy(1.0, 10.0),
            hardware_failure_threshold=3,
        )

    def test_manual_command_updates_hardware_and_state(self) -> None:
        state = self.service.set_manual(2, 3)
        self.assertEqual(self.actuator.applied, FanSetpoints(2.0, 3.0))
        self.assertEqual(state.mode, VentilationMode.MANUAL)

    def test_stop_is_explicit_state(self) -> None:
        self.service.set_manual(2, 3)
        state = self.service.stop()
        self.assertEqual(self.actuator.applied, FanSetpoints.stopped())
        self.assertEqual(state.mode, VentilationMode.STOP)

    def test_close_stops_before_closing(self) -> None:
        self.service.set_manual(2, 3)
        self.service.close()
        self.assertEqual(self.actuator.applied, FanSetpoints.stopped())
        self.assertTrue(self.actuator.closed)

    def test_first_health_failure_marks_output_unknown_without_alarm(self) -> None:
        self.service.set_manual(5, 0)
        self.actuator.fail_health = True
        state = self.service.health_check()
        self.assertFalse(state.hardware_ready)
        self.assertFalse(state.output_state_known)
        self.assertEqual(state.consecutive_hardware_failures, 1)
        self.assertEqual(state.active_alarms, ())

    def test_three_consecutive_failures_activate_dac_alarm(self) -> None:
        self.actuator.fail_health = True
        self.actuator.fail_recover = True
        for _ in range(3):
            state = self.service.health_check()
        self.assertEqual(state.mode, VentilationMode.FAULT)
        self.assertEqual(state.active_alarms[0].code, AlarmCode.DAC_COMMUNICATION_LOST)
        self.assertEqual(state.active_alarms[0].occurrences, 3)

    def test_recovery_forces_stop_and_does_not_restore_previous_voltage(self) -> None:
        self.service.set_manual(10, 0)
        self.actuator.fail_health = True
        self.service.health_check()
        self.actuator.fail_health = False
        state = self.service.health_check()
        self.assertEqual(self.actuator.recover_calls, 1)
        self.assertEqual(self.actuator.applied, FanSetpoints.stopped())
        self.assertEqual(state.mode, VentilationMode.STOP)
        self.assertTrue(state.output_state_known)
        self.assertTrue(state.hardware_ready)
        self.assertEqual(state.active_alarms, ())

    def test_command_failure_activates_alarm_immediately(self) -> None:
        self.actuator.fail_apply = True
        with self.assertRaises(RuntimeError):
            self.service.set_manual(5, 0)
        state = self.service.state()
        self.assertEqual(state.mode, VentilationMode.FAULT)
        self.assertEqual(state.active_alarms[0].code, AlarmCode.DAC_COMMUNICATION_LOST)

    def test_setpoint_is_rejected_until_recovery_completes(self) -> None:
        self.actuator.fail_health = True
        self.service.health_check()
        with self.assertRaises(HardwareFaultActiveError):
            self.service.set_manual(5, 0)

    def test_missing_dac_at_startup_is_visible_as_fault(self) -> None:
        actuator = FakeActuator(ready=False)
        service = VentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            hardware_failure_threshold=3,
        )
        state = service.state()
        self.assertEqual(state.mode, VentilationMode.FAULT)
        self.assertFalse(state.hardware_ready)
        self.assertFalse(state.output_state_known)
        self.assertEqual(state.active_alarms[0].code, AlarmCode.DAC_COMMUNICATION_LOST)

    def test_sensor_bus_is_visible_and_supervised_independently(self) -> None:
        sensor_bus = FakeSensorBus()
        service = VentilationService(
            self.actuator,
            FanSetpointPolicy(1.0, 10.0),
            sensor_bus=sensor_bus,
        )

        state = service.health_check()
        self.assertEqual(sensor_bus.health_calls, 1)
        self.assertIsNotNone(state.sensor_bus)
        self.assertEqual(state.sensor_bus.nodes[0].slave_address, 1)
        self.assertTrue(state.hardware_ready)

        sensor_bus.fail_health = True
        state = service.health_check()
        self.assertTrue(state.hardware_ready)
        self.assertEqual(state.mode, VentilationMode.STOP)
        self.assertEqual(state.active_alarms, ())

        service.close()
        self.assertTrue(sensor_bus.closed)

    def test_sensor_bus_closes_even_if_actuator_close_fails(self) -> None:
        sensor_bus = FakeSensorBus()
        self.actuator.fail_close = True
        service = VentilationService(
            self.actuator,
            FanSetpointPolicy(1.0, 10.0),
            sensor_bus=sensor_bus,
        )

        with self.assertRaisesRegex(RuntimeError, "Actuator close failed"):
            service.close()

        self.assertTrue(self.actuator.closed)
        self.assertTrue(sensor_bus.closed)


if __name__ == "__main__":
    unittest.main()
