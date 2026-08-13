import unittest

from ventilation_core.application.service import VentilationService
from ventilation_core.domain.models import FanSetpoints, VentilationMode
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.domain.tacho import FanTachoState, TachoMonitorState
from ventilation_core.infrastructure.tacho_monitor import TachoMonitorConfig
from ventilation_core.main import build_parser


class FakeActuator:
    def __init__(self) -> None:
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()
        self.closed = False

    def apply(self, setpoints: FanSetpoints) -> None:
        self.applied = setpoints

    def stop_all(self) -> None:
        self.applied = FanSetpoints.stopped()

    def health_check(self) -> None:
        pass

    def recover(self) -> None:
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()

    def close(self) -> None:
        self.closed = True


class FakeTachoMonitor:
    def __init__(self) -> None:
        self.health_calls = 0
        self.closed = False
        self.fail_health = False
        self.current_state = TachoMonitorState(
            chip_path="/dev/gpiochip0",
            ready=True,
            worker_alive=True,
            last_error=None,
            supply=FanTachoState(
                line_name="GPIO17",
                line_offset=17,
                frequency_hz=60.0,
                rpm=1200.0,
                sample_count=6,
                age_seconds=0.01,
                valid=True,
            ),
            extract=FanTachoState(
                line_name="GPIO27",
                line_offset=27,
                frequency_hz=70.0,
                rpm=1400.0,
                sample_count=6,
                age_seconds=0.01,
                valid=True,
            ),
        )

    def state(self) -> TachoMonitorState:
        return self.current_state

    def health_check(self) -> None:
        self.health_calls += 1
        if self.fail_health:
            raise RuntimeError("TACHO worker failure")

    def close(self) -> None:
        self.closed = True


class TachoRuntimeTests(unittest.TestCase):
    def test_core_state_exposes_supply_and_extract_tacho_read_only(self) -> None:
        actuator = FakeActuator()
        tacho = FakeTachoMonitor()
        service = VentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            tacho=tacho,
        )

        state = service.set_manual(4.0, 5.0)

        self.assertEqual(state.mode, VentilationMode.MANUAL)
        self.assertIsNotNone(state.tacho)
        self.assertTrue(state.tacho.supply.valid)
        self.assertEqual(state.tacho.supply.line_name, "GPIO17")
        self.assertEqual(state.tacho.supply.rpm, 1200.0)
        self.assertTrue(state.tacho.extract.valid)
        self.assertEqual(state.tacho.extract.line_name, "GPIO27")
        self.assertEqual(state.tacho.extract.rpm, 1400.0)
        self.assertEqual(actuator.applied, FanSetpoints(4.0, 5.0))

        payload = state.to_dict()
        self.assertEqual(payload["tacho"]["supply"]["rpm"], 1200.0)
        self.assertEqual(payload["tacho"]["extract"]["rpm"], 1400.0)

    def test_tacho_health_failure_does_not_fault_or_change_dac(self) -> None:
        actuator = FakeActuator()
        tacho = FakeTachoMonitor()
        service = VentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            tacho=tacho,
        )
        service.set_manual(4.0, 5.0)
        tacho.fail_health = True

        state = service.health_check()

        self.assertEqual(tacho.health_calls, 1)
        self.assertEqual(state.mode, VentilationMode.MANUAL)
        self.assertEqual(state.active_alarms, ())
        self.assertTrue(state.hardware_ready)
        self.assertEqual(actuator.applied, FanSetpoints(4.0, 5.0))

    def test_service_close_closes_tacho_monitor(self) -> None:
        actuator = FakeActuator()
        tacho = FakeTachoMonitor()
        service = VentilationService(
            actuator,
            FanSetpointPolicy(1.0, 10.0),
            tacho=tacho,
        )

        service.close()

        self.assertTrue(actuator.closed)
        self.assertTrue(tacho.closed)

    def test_tacho_runtime_is_opt_in_and_has_final_gpio_defaults(self) -> None:
        parser = build_parser()
        default_args = parser.parse_args([])
        self.assertFalse(default_args.enable_supply_tacho)
        self.assertFalse(default_args.enable_extract_tacho)
        self.assertEqual(default_args.tacho_chip, "/dev/gpiochip0")
        self.assertEqual(default_args.supply_tacho_line, "GPIO17")
        self.assertEqual(default_args.extract_tacho_line, "GPIO27")
        self.assertEqual(default_args.tacho_timeout, 0.25)
        self.assertEqual(default_args.tacho_averaging_periods, 6)

        enabled_args = parser.parse_args(
            ["--enable-supply-tacho", "--enable-extract-tacho"]
        )
        self.assertTrue(enabled_args.enable_supply_tacho)
        self.assertTrue(enabled_args.enable_extract_tacho)

    def test_tacho_config_rejects_duplicate_gpio_lines(self) -> None:
        with self.assertRaises(ValueError):
            TachoMonitorConfig(
                supply_line_name="GPIO17",
                extract_line_name="GPIO17",
            )

    def test_tacho_config_requires_at_least_one_channel(self) -> None:
        with self.assertRaises(ValueError):
            TachoMonitorConfig(
                supply_line_name=None,
                extract_line_name=None,
            )


if __name__ == "__main__":
    unittest.main()
