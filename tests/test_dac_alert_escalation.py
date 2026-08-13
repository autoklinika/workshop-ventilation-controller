import unittest

from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.alerting_service import AlertingVentilationService
from ventilation_core.domain.models import AlarmCode, AlarmSeverity, FanSetpoints, VentilationMode
from ventilation_core.domain.policy import FanSetpointPolicy


class FailingActuator:
    def __init__(self) -> None:
        self.ready = True
        self.last_error = None
        self.fail_health = True
        self.fail_recover = True
        self.applied = FanSetpoints.stopped()

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


class DacAlertEscalationTest(unittest.TestCase):
    def test_warning_escalates_to_critical_and_both_stay_in_history(self) -> None:
        actuator = FailingActuator()
        service = AlertingVentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            hardware_failure_threshold=3,
            alert_registry=AlertRegistry(MemoryAlertStore()),
        )

        first = service.health_check()
        self.assertEqual(first.mode, VentilationMode.STOP)
        self.assertEqual(first.active_alarms[0].code, AlarmCode.DAC_STATE_UNCERTAIN)
        self.assertEqual(first.active_alarms[0].severity, AlarmSeverity.WARNING)
        warning_id = first.active_alarms[0].alert_id

        service.health_check()
        third = service.health_check()
        self.assertEqual(third.mode, VentilationMode.FAULT)
        self.assertEqual(len(third.active_alarms), 1)
        self.assertEqual(third.active_alarms[0].code, AlarmCode.DAC_COMMUNICATION_LOST)
        self.assertEqual(third.active_alarms[0].severity, AlarmSeverity.CRITICAL)
        critical_id = third.active_alarms[0].alert_id
        self.assertNotEqual(warning_id, critical_id)

        actuator.fail_health = False
        actuator.fail_recover = False
        self.assertEqual(service.health_check().active_alarms, ())
        history = service.alert_history()
        ids = {record.alert_id for record in history}
        self.assertIn(warning_id, ids)
        self.assertIn(critical_id, ids)
        self.assertTrue(all(record.cleared_at is not None for record in history))
        service.close()


if __name__ == "__main__":
    unittest.main()
