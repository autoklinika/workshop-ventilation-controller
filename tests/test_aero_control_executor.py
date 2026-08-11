import unittest
from unittest.mock import patch

from ventilation_core.domain.aero_control import AeroControlCommand, AeroControlExecutionState
from ventilation_core.infrastructure.aero_control_executor import (
    AeroControlExecutorConfig,
    execute_control_change,
)
from ventilation_core.infrastructure.modbus_rtu import ModbusError


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class AeroControlExecutorTests(unittest.TestCase):
    def test_success_requires_readback_and_physical_fan_change(self) -> None:
        command = AeroControlCommand.set_speed(2)
        config = AeroControlExecutorConfig(
            execution_timeout_seconds=6.0,
            confirmation_poll_interval_seconds=2.0,
        )
        clock = FakeClock()
        reads = iter([
            [1],   # previous speed
            [20],  # baseline fan 1
            [20],  # baseline fan 2
            [2],   # readback target
            [20],  # first confirmation fan 1
            [20],  # first confirmation fan 2
            [35],  # second confirmation fan 1 -> physical change
            [35],  # second confirmation fan 2
        ])

        with patch(
            "ventilation_core.infrastructure.aero_control_executor.read_holding_registers",
            side_effect=lambda *args, **kwargs: next(reads),
        ), patch(
            "ventilation_core.infrastructure.aero_control_executor.write_single_register"
        ) as write:
            result = execute_control_change(
                object(),
                config,
                command,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

        self.assertEqual(result.state, AeroControlExecutionState.SUCCEEDED)
        self.assertTrue(result.physical_confirmation)
        self.assertFalse(result.recovered)
        self.assertEqual(result.previous_value, 1)
        self.assertEqual(result.readback_value, 2)
        write.assert_called_once()

    def test_noop_target_does_not_write(self) -> None:
        command = AeroControlCommand.set_airing(False)
        config = AeroControlExecutorConfig()
        reads = iter([[0], [0], [0]])

        with patch(
            "ventilation_core.infrastructure.aero_control_executor.read_holding_registers",
            side_effect=lambda *args, **kwargs: next(reads),
        ), patch(
            "ventilation_core.infrastructure.aero_control_executor.write_single_register"
        ) as write:
            result = execute_control_change(object(), config, command)

        self.assertTrue(result.succeeded)
        self.assertTrue(result.physical_confirmation)
        write.assert_not_called()

    def test_readback_failure_restores_previous_value(self) -> None:
        command = AeroControlCommand.set_speed(3)
        config = AeroControlExecutorConfig()
        reads = iter([
            [1],   # previous
            [10], [10],  # baseline
            [2],   # bad target readback
            [1],   # recovery readback
        ])

        with patch(
            "ventilation_core.infrastructure.aero_control_executor.read_holding_registers",
            side_effect=lambda *args, **kwargs: next(reads),
        ), patch(
            "ventilation_core.infrastructure.aero_control_executor.write_single_register"
        ) as write:
            result = execute_control_change(object(), config, command)

        self.assertEqual(result.state, AeroControlExecutionState.FAILED)
        self.assertTrue(result.recovered)
        self.assertIn("readback mismatch", result.error or "")
        self.assertEqual(write.call_count, 2)

    def test_physical_timeout_restores_previous_value(self) -> None:
        command = AeroControlCommand.set_airing(True)
        config = AeroControlExecutorConfig(
            execution_timeout_seconds=4.0,
            confirmation_poll_interval_seconds=2.0,
        )
        clock = FakeClock()
        reads = iter([
            [0],   # previous airing
            [15], [15],  # baseline
            [1],   # target readback
            [15], [15],  # confirmation 1 unchanged
            [15], [15],  # confirmation 2 unchanged
            [0],   # recovery readback
        ])

        with patch(
            "ventilation_core.infrastructure.aero_control_executor.read_holding_registers",
            side_effect=lambda *args, **kwargs: next(reads),
        ), patch(
            "ventilation_core.infrastructure.aero_control_executor.write_single_register"
        ) as write:
            result = execute_control_change(
                object(),
                config,
                command,
                monotonic=clock.monotonic,
                sleep=clock.sleep,
            )

        self.assertEqual(result.state, AeroControlExecutionState.FAILED)
        self.assertFalse(result.physical_confirmation)
        self.assertTrue(result.recovered)
        self.assertIn("not confirmed", result.error or "")
        self.assertEqual(write.call_count, 2)

    def test_protocol_failure_attempts_recovery(self) -> None:
        command = AeroControlCommand.set_speed(1)
        config = AeroControlExecutorConfig()
        reads = iter([[0], [0], [0], [0]])
        calls = 0

        def fake_write(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ModbusError("write failed")

        with patch(
            "ventilation_core.infrastructure.aero_control_executor.read_holding_registers",
            side_effect=lambda *args, **kwargs: next(reads),
        ), patch(
            "ventilation_core.infrastructure.aero_control_executor.write_single_register",
            side_effect=fake_write,
        ):
            result = execute_control_change(object(), config, command)

        self.assertEqual(result.state, AeroControlExecutionState.FAILED)
        self.assertTrue(result.recovered)
        self.assertIn("write failed", result.error or "")


if __name__ == "__main__":
    unittest.main()
