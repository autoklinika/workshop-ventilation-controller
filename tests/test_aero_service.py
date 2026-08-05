import unittest

from ventilation_core.application.service import VentilationService
from ventilation_core.domain.aero import AeroBusState, AeroTelemetry
from ventilation_core.domain.models import FanSetpoints, VentilationMode
from ventilation_core.domain.policy import FanSetpointPolicy


class FakeActuator:
    ready = True
    last_error = None

    def __init__(self) -> None:
        self.applied = FanSetpoints.stopped()
        self.closed = False
        self.health_calls = 0

    def apply(self, setpoints: FanSetpoints) -> None:
        self.applied = setpoints

    def stop_all(self) -> None:
        self.applied = FanSetpoints.stopped()

    def health_check(self) -> None:
        self.health_calls += 1

    def recover(self) -> None:
        self.ready = True
        self.applied = FanSetpoints.stopped()

    def close(self) -> None:
        self.closed = True


class FakeAeroBus:
    def __init__(self) -> None:
        self.health_calls = 0
        self.closed = False
        self.fail_health = False
        self.current_state = AeroBusState(
            port="/dev/ttyAMA4",
            baudrate=9600,
            slave_address=44,
            register_addresses=(2016, 2021, 2022, 2023, 2033, 2034),
            inter_register_delay_seconds=0.05,
            poll_interval_seconds=2.0,
            ready=True,
            worker_alive=True,
            online=True,
            usable=True,
            telemetry=AeroTelemetry(
                humidity_percent=45.0,
                supply_temperature_celsius=21.0,
                extract_temperature_celsius=22.0,
                outdoor_temperature_celsius=7.0,
                fan_1_percent=40,
                fan_2_percent=42,
            ),
        )

    def state(self) -> AeroBusState:
        return self.current_state

    def health_check(self) -> None:
        self.health_calls += 1
        if self.fail_health:
            raise RuntimeError("AERO worker stopped")

    def close(self) -> None:
        self.closed = True


class AeroServiceIntegrationTest(unittest.TestCase):
    def test_aero_bus_is_visible_and_failure_does_not_fault_dac(self) -> None:
        actuator = FakeActuator()
        aero_bus = FakeAeroBus()
        service = VentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            aero_bus=aero_bus,
        )

        state = service.health_check()
        self.assertEqual(aero_bus.health_calls, 1)
        self.assertIsNotNone(state.aero_bus)
        self.assertTrue(state.aero_bus.online)
        self.assertTrue(state.hardware_ready)

        aero_bus.fail_health = True
        state = service.health_check()
        self.assertTrue(state.hardware_ready)
        self.assertEqual(state.mode, VentilationMode.STOP)
        self.assertEqual(state.active_alarms, ())

        service.close()
        self.assertTrue(aero_bus.closed)
        self.assertTrue(actuator.closed)


if __name__ == "__main__":
    unittest.main()
