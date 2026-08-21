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
    AeroControlRequest,
    AeroControlResponse,
    _execute_queued_control,
    _publish_control_result,
    _wait_for_matching_control_result,
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
        command_queue.put_nowait(
            AeroControlRequest("request-1", AeroControlCommand.set_speed(1))
        )

        with self.assertRaises(queue.Full):
            command_queue.put_nowait(
                AeroControlRequest("request-2", AeroControlCommand.set_speed(2))
            )

    def test_waiter_discards_late_result_from_timed_out_previous_request(self) -> None:
        result_queue: queue.Queue = queue.Queue()
        stale_command = AeroControlCommand.set_speed(2)
        current_command = AeroControlCommand.set_speed(0)
        stale_result = AeroControlResult(
            command=stale_command,
            state=AeroControlExecutionState.SUCCEEDED,
            previous_value=1,
            readback_value=2,
            physical_confirmation=True,
        )
        current_result = AeroControlResult(
            command=current_command,
            state=AeroControlExecutionState.SUCCEEDED,
            previous_value=2,
            readback_value=0,
            physical_confirmation=True,
        )
        result_queue.put_nowait(AeroControlResponse("timed-out-request", stale_result))
        result_queue.put_nowait(AeroControlResponse("current-request", current_result))

        received = _wait_for_matching_control_result(
            result_queue,
            "current-request",
            0.1,
        )

        self.assertIs(received, current_result)
        self.assertEqual(received.command.kind.value, "speed")
        self.assertEqual(received.command.value, 0)

    def test_worker_replaces_abandoned_stale_result_in_single_slot_queue(self) -> None:
        result_queue: queue.Queue = queue.Queue(maxsize=1)
        old_result = AeroControlResult(
            command=AeroControlCommand.set_speed(2),
            state=AeroControlExecutionState.SUCCEEDED,
            previous_value=1,
            readback_value=2,
            physical_confirmation=True,
        )
        new_result = AeroControlResult(
            command=AeroControlCommand.set_speed(0),
            state=AeroControlExecutionState.SUCCEEDED,
            previous_value=2,
            readback_value=0,
            physical_confirmation=True,
        )
        result_queue.put_nowait(AeroControlResponse("old", old_result))

        _publish_control_result(
            result_queue,
            AeroControlResponse("new", new_result),
        )

        response = result_queue.get_nowait()
        self.assertEqual(response.request_id, "new")
        self.assertIs(response.result, new_result)


if __name__ == "__main__":
    unittest.main()
