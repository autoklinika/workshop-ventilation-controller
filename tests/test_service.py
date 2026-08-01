import unittest

from ventilation_core.application.service import VentilationService
from ventilation_core.domain.models import FanSetpoints, VentilationMode
from ventilation_core.domain.policy import FanSetpointPolicy


class FakeActuator:
    def __init__(self) -> None:
        self.ready = True
        self.applied = FanSetpoints.stopped()
        self.closed = False

    def apply(self, setpoints: FanSetpoints) -> None:
        self.applied = setpoints

    def stop_all(self) -> None:
        self.applied = FanSetpoints.stopped()

    def health_check(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class VentilationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.actuator = FakeActuator()
        self.service = VentilationService(
            self.actuator,
            FanSetpointPolicy(1.0, 10.0),
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
