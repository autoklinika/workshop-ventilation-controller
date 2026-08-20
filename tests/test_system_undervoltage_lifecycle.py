from __future__ import annotations

import unittest

from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.alerting_service import AlertingVentilationService
from ventilation_core.domain.models import AlarmCode, AlarmSeverity, FanSetpoints
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.infrastructure.system_power_monitor import SystemPowerState


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
    def __init__(self) -> None:
        self.current_state = SystemPowerState(
            available=True,
            undervoltage_now=True,
            undervoltage_occurred=True,
            throttled_mask=0x10001,
        )

    def poll(self) -> SystemPowerState:
        return self.current_state

    def state(self) -> SystemPowerState:
        return self.current_state

    def close(self) -> None:
        return


class SystemUndervoltageLifecycleTest(unittest.TestCase):
    def test_active_ack_clear_history_lifecycle_is_persistent_and_non_control(self) -> None:
        actuator = FakeActuator()
        monitor = FakePowerMonitor()
        service = AlertingVentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            alert_registry=AlertRegistry(MemoryAlertStore()),
            system_power_monitor=monitor,
        )

        active_state = service.health_check()
        self.assertEqual(len(active_state.active_alarms), 1)
        active_alarm = active_state.active_alarms[0]
        self.assertEqual(active_alarm.code, AlarmCode.SYSTEM_UNDERVOLTAGE)
        self.assertEqual(active_alarm.severity, AlarmSeverity.CRITICAL)
        self.assertEqual(active_alarm.source, "system_power")

        active_record = service.active_alerts()[0]
        alert_id = active_record.alert_id
        self.assertIsNotNone(alert_id)
        self.assertFalse(active_record.acknowledged)
        self.assertIsNone(active_record.cleared_at)

        acknowledged = service.acknowledge_alert(alert_id)
        self.assertTrue(acknowledged.acknowledged)
        self.assertIsNotNone(acknowledged.acknowledged_at)
        self.assertIsNone(acknowledged.cleared_at)

        still_active = service.active_alerts()[0]
        self.assertEqual(still_active.alert_id, alert_id)
        self.assertTrue(still_active.acknowledged)

        monitor.current_state = SystemPowerState(
            available=True,
            undervoltage_now=False,
            undervoltage_occurred=True,
            throttled_mask=0x10000,
        )
        cleared_state = service.health_check()
        self.assertEqual(cleared_state.active_alarms, ())
        self.assertEqual(service.active_alerts(), ())

        history = service.alert_history()
        self.assertGreaterEqual(len(history), 1)
        cleared = next(record for record in history if record.alert_id == alert_id)
        self.assertTrue(cleared.acknowledged)
        self.assertIsNotNone(cleared.acknowledged_at)
        self.assertIsNotNone(cleared.cleared_at)
        self.assertEqual(cleared.code, AlarmCode.SYSTEM_UNDERVOLTAGE)

        # The diagnostic alert never blocks or changes fan control authority.
        monitor.current_state = SystemPowerState(
            available=True,
            undervoltage_now=True,
            undervoltage_occurred=True,
            throttled_mask=0x10001,
        )
        service.health_check()
        running = service.set_manual(2.0, 2.0)
        self.assertEqual(actuator.applied, FanSetpoints(2.0, 2.0))
        self.assertEqual(running.setpoints, FanSetpoints(2.0, 2.0))

        service.close()


if __name__ == "__main__":
    unittest.main()
