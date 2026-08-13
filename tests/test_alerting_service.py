import unittest

from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.alerting_service import AlertingVentilationService
from ventilation_core.domain.aero import AeroBusState
from ventilation_core.domain.models import AlarmCode, FanSetpoints, VentilationMode
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.domain.sensors import SensorBusState, SensorNodeState
from ventilation_core.domain.tacho import FanTachoState, TachoMonitorState


class FakeActuator:
    def __init__(self) -> None:
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()
        self.fail_health = False
        self.fail_recover = False

    def apply(self, setpoints: FanSetpoints) -> None:
        self.applied = setpoints

    def stop_all(self) -> None:
        self.applied = FanSetpoints.stopped()

    def health_check(self) -> None:
        if self.fail_health:
            self.ready = False
            self.last_error = "DAC timeout"
            raise RuntimeError(self.last_error)

    def recover(self) -> None:
        if self.fail_recover:
            self.ready = False
            self.last_error = "DAC timeout"
            raise RuntimeError(self.last_error)
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()

    def close(self) -> None:
        return


class FakeSensorBus:
    def __init__(self, state: SensorBusState) -> None:
        self.current_state = state
    def state(self) -> SensorBusState: return self.current_state
    def health_check(self) -> None: return
    def close(self) -> None: return


class FakeAeroBus:
    def __init__(self, state: AeroBusState) -> None:
        self.current_state = state
    def state(self) -> AeroBusState: return self.current_state
    def health_check(self) -> None: return
    def close(self) -> None: return


class FakeTacho:
    def __init__(self, state: TachoMonitorState) -> None:
        self.current_state = state
    def state(self) -> TachoMonitorState: return self.current_state
    def health_check(self) -> None: return
    def close(self) -> None: return


def registry() -> AlertRegistry:
    return AlertRegistry(MemoryAlertStore())


def tacho_channel(name: str) -> FanTachoState:
    return FanTachoState(line_name=name, line_offset=17 if name == "GPIO17" else 27, frequency_hz=0.0, rpm=0.0, sample_count=0, age_seconds=None, valid=False)


class AlertingVentilationServiceTest(unittest.TestCase):
    def test_sensor_warning_does_not_fault_or_block_fans(self) -> None:
        actuator = FakeActuator()
        sensor_bus = FakeSensorBus(SensorBusState(port="/dev/ttyAMA0", baudrate=19200, addresses=(1,), ready=True, worker_alive=True, nodes=(SensorNodeState(slave_address=1, online=False, usable=False, polls=5, consecutive_failures=3, last_error="Modbus timeout"),)))
        service = AlertingVentilationService(actuator, FanSetpointPolicy(1.0, 10.0), sensor_bus=sensor_bus, alert_registry=registry())
        state = service.health_check()
        self.assertEqual(state.mode, VentilationMode.STOP)
        self.assertEqual(state.active_alarms[0].code, AlarmCode.SENSOR_NODE_UNAVAILABLE)
        self.assertIsNotNone(state.active_alarms[0].alert_id)
        state = service.set_manual(2.0, 2.0)
        self.assertEqual(state.mode, VentilationMode.MANUAL)
        self.assertEqual(actuator.applied, FanSetpoints(2.0, 2.0))
        service.close()

    def test_aero_failure_becomes_warning_without_changing_dac_policy(self) -> None:
        actuator = FakeActuator()
        aero = FakeAeroBus(AeroBusState(port="/dev/ttyAMA4", baudrate=9600, slave_address=44, register_addresses=(2016,), inter_register_delay_seconds=0.05, poll_interval_seconds=2.0, ready=True, worker_alive=True, online=False, usable=False, consecutive_failures=3, last_error="timeout"))
        service = AlertingVentilationService(actuator, FanSetpointPolicy(1.0, 10.0), aero_bus=aero, alert_registry=registry())
        state = service.health_check()
        self.assertEqual(state.active_alarms[0].code, AlarmCode.AERO_BUS_UNAVAILABLE)
        self.assertEqual(state.mode, VentilationMode.STOP)
        service.close()

    def test_missing_tacho_pulses_are_not_alert_when_monitor_is_healthy(self) -> None:
        actuator = FakeActuator()
        tacho = FakeTacho(TachoMonitorState(chip_path="/dev/gpiochip0", ready=True, worker_alive=True, last_error=None, supply=tacho_channel("GPIO17"), extract=tacho_channel("GPIO27")))
        service = AlertingVentilationService(actuator, FanSetpointPolicy(1.0, 10.0), tacho=tacho, alert_registry=registry(), required_tacho_channels=("supply", "extract"))
        self.assertEqual(service.health_check().active_alarms, ())
        service.close()

    def test_tacho_monitor_error_and_missing_channel_are_alerts(self) -> None:
        actuator = FakeActuator()
        tacho = FakeTacho(TachoMonitorState(chip_path="/dev/gpiochip0", ready=False, worker_alive=True, last_error="GPIO request failed", supply=tacho_channel("GPIO17"), extract=None))
        service = AlertingVentilationService(actuator, FanSetpointPolicy(1.0, 10.0), tacho=tacho, alert_registry=registry(), required_tacho_channels=("supply", "extract"))
        codes = {alarm.code for alarm in service.health_check().active_alarms}
        self.assertIn(AlarmCode.TACHO_MONITOR_UNAVAILABLE, codes)
        self.assertIn(AlarmCode.TACHO_CONFIGURATION_INVALID, codes)
        service.close()

    def test_dac_ack_is_persisted_until_recovery(self) -> None:
        actuator = FakeActuator()
        service = AlertingVentilationService(actuator, FanSetpointPolicy(1.0, 10.0), hardware_failure_threshold=3, alert_registry=registry())
        actuator.fail_health = True
        actuator.fail_recover = True
        for _ in range(3):
            state = service.health_check()
        self.assertEqual(state.mode, VentilationMode.FAULT)
        self.assertEqual(state.active_alarms[0].code, AlarmCode.DAC_COMMUNICATION_LOST)
        alert_id = state.active_alarms[0].alert_id
        service.acknowledge_alert(alert_id)
        self.assertTrue(service.state().active_alarms[0].acknowledged)
        actuator.fail_health = False
        actuator.fail_recover = False
        self.assertEqual(service.health_check().active_alarms, ())
        history = service.alert_history()
        self.assertEqual(history[0].alert_id, alert_id)
        self.assertTrue(history[0].acknowledged)
        self.assertIsNotNone(history[0].cleared_at)
        service.close()


if __name__ == "__main__":
    unittest.main()
