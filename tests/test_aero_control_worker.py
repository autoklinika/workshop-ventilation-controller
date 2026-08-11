import queue
import unittest
from unittest.mock import patch

from ventilation_core.domain.aero import AeroBusState
from ventilation_core.domain.aero_control import (
    AeroControlCommand,
    AeroControlExecutionState,
    AeroControlResult,
)
from ventilation_core.infrastructure.aero_bus_worker import (
    AeroBusConfig,
    _execute_queued_control,
)


def ready_state(config: AeroBusConfig) -> AeroBusState:
    return AeroBusState(
        port=config.port,
        baudrate=config.baudrate,
        slave_address=config.slave_address,
        register_addresses=config.register_addresses,
        inter_register_delay_seconds=config.inter_register_delay_seconds,
        poll_interval_seconds=config.poll_interval_seconds,
        ready=True,
        worker_alive=True,
        online=True,
        usable=True,
    )


class FakeStateQueue:
    def __init__(self) -> None:
        self.items = []

    def put_nowait(self, item) -> None:
        self.items.append(item)


class AeroControlWorkerTests(unittest.TestCase):
    def test_control_is_executed_inside_uart_owner_and_result_is_published(self) -> None:
        config = AeroBusConfig()
        state = ready_state(config)
        command = AeroControlCommand.set_speed(1)
        expected = AeroControlResult(
            command=command,
            state=AeroControlExecutionState.SUCCEEDED,
            previous_value=0,
            readback_value=1,
            physical_confirmation=True,
        )
        state_queue = FakeStateQueue()

        with patch(
            "ventilation_core.infrastructure.aero_bus_worker.execute_control_change",
            return_value=expected,
        ) as executor:
            completed, result = _execute_queued_control(
                object(), config, state, command, state_queue
            )

        executor.assert_called_once()
        self.assertIs(result, expected)
        self.assertGreaterEqual(len(state_queue.items), 2)
        self.assertTrue(state_queue.items[0].control_busy)
        self.assertFalse(completed.control_busy)
        self.assertIs(completed.last_control_result, expected)

    def test_failed_control_result_does_not_mark_bus_transport_offline(self) -> None:
        config = AeroBusConfig()
        state = ready_state(config)
        command = AeroControlCommand.set_airing(True)
        failed = AeroControlResult(
            command=command,
            state=AeroControlExecutionState.FAILED,
            previous_value=0,
            recovered=True,
            error="physical confirmation timeout",
        )
        state_queue = FakeStateQueue()

        with patch(
            "ventilation_core.infrastructure.aero_bus_worker.execute_control_change",
            return_value=failed,
        ):
            completed, _ = _execute_queued_control(
                object(), config, state, command, state_queue
            )

        self.assertTrue(completed.online)
        self.assertTrue(completed.usable)
        self.assertFalse(completed.control_busy)
        self.assertEqual(completed.last_control_result.state, AeroControlExecutionState.FAILED)

    def test_single_slot_command_queue_rejects_second_pending_command(self) -> None:
        command_queue: queue.Queue = queue.Queue(maxsize=1)
        command_queue.put_nowait(AeroControlCommand.set_speed(1))

        with self.assertRaises(queue.Full):
            command_queue.put_nowait(AeroControlCommand.set_speed(2))


if __name__ == "__main__":
    unittest.main()
