import unittest
from threading import Event, Thread

from ventilation_core.application.service import (
    AeroControlUnavailableError,
    VentilationService,
)
from ventilation_core.domain.aero import AeroBusState, AeroTelemetry
from ventilation_core.domain.aero_control import (
    AeroControlCommand,
    AeroControlExecutionState,
    AeroControlResult,
)
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


class BlockingAeroBus(FakeAeroBus):
    def __init__(self) -> None:
        super().__init__()
        self.control_started = Event()
        self.control_release = Event()
        self.execute_calls = 0

    def execute_control(self, command: AeroControlCommand) -> AeroControlResult:
        self.execute_calls += 1
        self.control_started.set()
        if not self.control_release.wait(timeout=5.0):
            raise TimeoutError("test AERO control release timeout")
        return AeroControlResult(
            command=command,
            state=AeroControlExecutionState.SUCCEEDED,
            physical_confirmation=True,
        )


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

    def test_state_remains_available_while_aero_control_waits(self) -> None:
        actuator = FakeActuator()
        aero_bus = BlockingAeroBus()
        service = VentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            aero_bus=aero_bus,
        )
        command = AeroControlCommand.set_speed(1)
        control_result: list[AeroControlResult] = []
        control_errors: list[BaseException] = []

        def run_control() -> None:
            try:
                control_result.append(service.control_aero(command))
            except BaseException as exc:  # pragma: no cover - asserted below
                control_errors.append(exc)

        control_thread = Thread(target=run_control, daemon=True)
        control_thread.start()
        self.assertTrue(aero_bus.control_started.wait(timeout=1.0))

        state_result = []
        state_done = Event()

        def read_state() -> None:
            state_result.append(service.state())
            state_done.set()

        state_thread = Thread(target=read_state, daemon=True)
        state_thread.start()
        try:
            self.assertTrue(
                state_done.wait(timeout=1.0),
                "service.state() blocked behind long-running AERO control",
            )
            self.assertTrue(state_result[0].hardware_ready)
            self.assertIsNotNone(state_result[0].aero_bus)
        finally:
            aero_bus.control_release.set()
            control_thread.join(timeout=2.0)
            state_thread.join(timeout=2.0)

        self.assertFalse(control_errors)
        self.assertEqual(len(control_result), 1)
        self.assertTrue(control_result[0].succeeded)
        service.close()

    def test_second_aero_control_is_rejected_while_first_is_in_progress(self) -> None:
        actuator = FakeActuator()
        aero_bus = BlockingAeroBus()
        service = VentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            aero_bus=aero_bus,
        )
        first_errors: list[BaseException] = []

        def run_first() -> None:
            try:
                service.control_aero(AeroControlCommand.set_speed(1))
            except BaseException as exc:  # pragma: no cover - asserted below
                first_errors.append(exc)

        first_thread = Thread(target=run_first, daemon=True)
        first_thread.start()
        self.assertTrue(aero_bus.control_started.wait(timeout=1.0))

        second_done = Event()
        second_errors: list[BaseException] = []

        def run_second() -> None:
            try:
                service.control_aero(AeroControlCommand.set_speed(2))
            except BaseException as exc:
                second_errors.append(exc)
            finally:
                second_done.set()

        second_thread = Thread(target=run_second, daemon=True)
        second_thread.start()
        try:
            self.assertTrue(
                second_done.wait(timeout=1.0),
                "second AERO command waited instead of being rejected immediately",
            )
            self.assertEqual(len(second_errors), 1)
            self.assertIsInstance(second_errors[0], AeroControlUnavailableError)
            self.assertEqual(str(second_errors[0]), "AERO control command already in progress")
            self.assertEqual(aero_bus.execute_calls, 1)
        finally:
            aero_bus.control_release.set()
            first_thread.join(timeout=2.0)
            second_thread.join(timeout=2.0)

        self.assertFalse(first_errors)
        service.close()


if __name__ == "__main__":
    unittest.main()
