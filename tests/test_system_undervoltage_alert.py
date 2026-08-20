from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from ventilation_core.alert_policy import load_alert_policy
from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.alerting_service import AlertingVentilationService
from ventilation_core.domain.models import AlarmCode, AlarmSeverity, FanSetpoints, VentilationMode
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.infrastructure.system_power_monitor import (
    RaspberryPiSystemPowerMonitor,
    SystemPowerState,
)
from ventilation_core.main import build_parser


ROOT = Path(__file__).resolve().parents[1]


class FakeActuator:
    def __init__(self) -> None:
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()

    def apply(self, setpoints: FanSetpoints) -> None:
        self.applied = setpoints

    def stop_all(self) -> None:
        self.applied = FanSetpoints.stopped()

    def health_check(self) -> None:
        return

    def recover(self) -> None:
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()

    def close(self) -> None:
        return


class FakePowerMonitor:
    def __init__(self, state: SystemPowerState) -> None:
        self.current_state = state
        self.polls = 0
        self.closed = False

    def poll(self) -> SystemPowerState:
        self.polls += 1
        return self.current_state

    def state(self) -> SystemPowerState:
        return self.current_state

    def close(self) -> None:
        self.closed = True


class RunnerSequence:
    def __init__(self, *items: object) -> None:
        self.items = list(items)

    def __call__(self, *args: object, **kwargs: object) -> object:
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class SystemUndervoltageAlertTest(unittest.TestCase):
    def test_vcgencmd_parser_uses_current_bit_zero_and_latched_bit_sixteen(self) -> None:
        runner = RunnerSequence(
            SimpleNamespace(returncode=0, stdout="throttled=0x10001\n", stderr=""),
            SimpleNamespace(returncode=0, stdout="throttled=0x10000\n", stderr=""),
        )
        monitor = RaspberryPiSystemPowerMonitor(runner=runner)

        active = monitor.poll()
        self.assertTrue(active.available)
        self.assertTrue(active.undervoltage_now)
        self.assertTrue(active.undervoltage_occurred)
        self.assertEqual(active.throttled_mask, 0x10001)

        historical_only = monitor.poll()
        self.assertTrue(historical_only.available)
        self.assertFalse(historical_only.undervoltage_now)
        self.assertTrue(historical_only.undervoltage_occurred)
        self.assertEqual(historical_only.throttled_mask, 0x10000)

    def test_real_cm5_latched_mask_0x50000_is_not_current_undervoltage(self) -> None:
        runner = RunnerSequence(
            SimpleNamespace(returncode=0, stdout="throttled=0x50000\n", stderr=""),
        )
        monitor = RaspberryPiSystemPowerMonitor(runner=runner)

        state = monitor.poll()

        self.assertTrue(state.available)
        self.assertFalse(state.undervoltage_now)
        self.assertTrue(state.undervoltage_occurred)
        self.assertEqual(state.throttled_mask, 0x50000)

    def test_monitor_does_not_treat_latched_history_bit_as_active_undervoltage(self) -> None:
        monitor = FakePowerMonitor(
            SystemPowerState(
                available=True,
                undervoltage_now=False,
                undervoltage_occurred=True,
                throttled_mask=0x10000,
            )
        )
        service = AlertingVentilationService(
            FakeActuator(),
            FanSetpointPolicy(1.0, 10.0),
            alert_registry=AlertRegistry(MemoryAlertStore()),
            system_power_monitor=monitor,
        )

        self.assertEqual(service.health_check().active_alarms, ())
        service.close()

    def test_active_undervoltage_is_critical_persistent_alert_but_does_not_block_control(self) -> None:
        actuator = FakeActuator()
        monitor = FakePowerMonitor(
            SystemPowerState(
                available=True,
                undervoltage_now=True,
                undervoltage_occurred=True,
                throttled_mask=0x10001,
            )
        )
        service = AlertingVentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            alert_registry=AlertRegistry(MemoryAlertStore()),
            system_power_monitor=monitor,
        )

        state = service.health_check()
        self.assertEqual(len(state.active_alarms), 1)
        alert = state.active_alarms[0]
        self.assertEqual(alert.code, AlarmCode.SYSTEM_UNDERVOLTAGE)
        self.assertEqual(alert.severity, AlarmSeverity.CRITICAL)
        self.assertEqual(alert.source, "system_power")
        self.assertIn("get_throttled=0x10001", alert.last_error)
        self.assertEqual(state.mode, VentilationMode.STOP)

        running = service.set_manual(2.0, 2.0)
        self.assertEqual(running.mode, VentilationMode.MANUAL)
        self.assertEqual(actuator.applied, FanSetpoints(2.0, 2.0))
        self.assertEqual(running.active_alarms[0].code, AlarmCode.SYSTEM_UNDERVOLTAGE)

        monitor.current_state = SystemPowerState(
            available=True,
            undervoltage_now=False,
            undervoltage_occurred=True,
            throttled_mask=0x10000,
        )
        cleared = service.health_check()
        self.assertEqual(cleared.active_alarms, ())
        history = service.alert_history()
        self.assertEqual(history[0].code, AlarmCode.SYSTEM_UNDERVOLTAGE)
        self.assertIsNotNone(history[0].cleared_at)
        service.close()
        self.assertTrue(monitor.closed)

    def test_failed_diagnostic_read_cannot_clear_previously_active_undervoltage(self) -> None:
        runner = RunnerSequence(
            SimpleNamespace(returncode=0, stdout="throttled=0x1\n", stderr=""),
            RuntimeError("mailbox unavailable"),
            SimpleNamespace(returncode=0, stdout="throttled=0x0\n", stderr=""),
        )
        monitor = RaspberryPiSystemPowerMonitor(runner=runner)

        self.assertTrue(monitor.poll().undervoltage_now)
        failed = monitor.poll()
        self.assertFalse(failed.available)
        self.assertTrue(failed.undervoltage_now)
        self.assertIn("mailbox unavailable", failed.last_error or "")

        recovered = monitor.poll()
        self.assertTrue(recovered.available)
        self.assertFalse(recovered.undervoltage_now)

    def test_invalid_vcgencmd_output_is_diagnostic_failure_not_false_alarm(self) -> None:
        runner = RunnerSequence(
            SimpleNamespace(returncode=0, stdout="garbage\n", stderr=""),
        )
        monitor = RaspberryPiSystemPowerMonitor(runner=runner)
        state = monitor.poll()
        self.assertFalse(state.available)
        self.assertIsNone(state.undervoltage_now)
        self.assertEqual(state.consecutive_failures, 1)
        self.assertIn("unexpected vcgencmd", state.last_error or "")

    def test_core_parser_enables_read_only_power_monitor_by_default(self) -> None:
        args = build_parser().parse_args([])
        self.assertFalse(args.disable_system_power_monitor)
        self.assertEqual(args.system_power_command, "/usr/bin/vcgencmd")
        self.assertEqual(args.system_power_timeout, 0.5)

    def test_alert_v2_policy_maps_undervoltage_without_control_reaction(self) -> None:
        policy = load_alert_policy(ROOT / "config" / "alerts-v2.default.toml")
        entry = policy.get(AlarmCode.SYSTEM_UNDERVOLTAGE.value)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertTrue(entry.enabled)
        self.assertEqual(entry.weight, 4)
        self.assertEqual(entry.severity, "critical")
        self.assertEqual(entry.hmi_color, "red")
        self.assertFalse(entry.affects_control)
        self.assertEqual(entry.category, "power")


if __name__ == "__main__":
    unittest.main()
