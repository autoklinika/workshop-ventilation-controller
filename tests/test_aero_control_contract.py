import struct
import unittest

from ventilation_core.domain.aero_control import (
    AERO_AIRING_REGISTER,
    AERO_CONFIRMATION_POLL_INTERVAL_SECONDS,
    AERO_EXECUTION_TIMEOUT_SECONDS,
    AERO_SPEED_REGISTER,
    AeroControlCommand,
    AeroControlExecutionState,
)
from ventilation_core.infrastructure.modbus_rtu import (
    ModbusError,
    append_crc,
    write_single_register,
)


class FakePort:
    timeout = 0.1

    def __init__(self, response: bytes = b"") -> None:
        self.response = bytearray(response)
        self.written = b""
        self.input_resets = 0
        self.flushed = False

    def reset_input_buffer(self) -> None:
        self.input_resets += 1

    def write(self, data: bytes) -> int:
        self.written = data
        return len(data)

    def flush(self) -> None:
        self.flushed = True

    def read(self, size: int) -> bytes:
        chunk = bytes(self.response[:size])
        del self.response[:size]
        return chunk


class AeroControlContractTests(unittest.TestCase):
    def test_speed_contract_is_limited_to_register_1080_and_values_0_to_3(self) -> None:
        for speed in range(4):
            command = AeroControlCommand.set_speed(speed)
            self.assertEqual(command.register_address, AERO_SPEED_REGISTER)
            self.assertEqual(command.value, speed)

        with self.assertRaisesRegex(ValueError, "speed must be"):
            AeroControlCommand.set_speed(4)

    def test_airing_contract_is_limited_to_register_1081_and_binary_values(self) -> None:
        off = AeroControlCommand.set_airing(False)
        on = AeroControlCommand.set_airing(True)
        self.assertEqual((off.register_address, off.value), (AERO_AIRING_REGISTER, 0))
        self.assertEqual((on.register_address, on.value), (AERO_AIRING_REGISTER, 1))

    def test_stage3b_timing_contract_matches_hardware_validation(self) -> None:
        self.assertEqual(AERO_EXECUTION_TIMEOUT_SECONDS, 60.0)
        self.assertEqual(AERO_CONFIRMATION_POLL_INTERVAL_SECONDS, 2.0)

    def test_execution_states_include_physical_confirmation_and_recovery(self) -> None:
        self.assertIn(
            AeroControlExecutionState.WAITING_PHYSICAL_CONFIRMATION,
            tuple(AeroControlExecutionState),
        )
        self.assertIn(
            AeroControlExecutionState.RECOVERY_PENDING,
            tuple(AeroControlExecutionState),
        )

    def test_fc06_requires_exact_echo(self) -> None:
        request = append_crc(struct.pack(">BBHH", 44, 6, AERO_SPEED_REGISTER, 2))
        port = FakePort(request)

        write_single_register(
            port,
            slave_address=44,
            register_address=AERO_SPEED_REGISTER,
            value=2,
            timeout_seconds=0.1,
        )

        self.assertEqual(port.written, request)
        self.assertEqual(port.input_resets, 1)
        self.assertTrue(port.flushed)

    def test_fc06_rejects_echo_with_different_value(self) -> None:
        response = append_crc(struct.pack(">BBHH", 44, 6, AERO_SPEED_REGISTER, 3))
        port = FakePort(response)

        with self.assertRaisesRegex(ModbusError, "FC06 echo mismatch"):
            write_single_register(
                port,
                slave_address=44,
                register_address=AERO_SPEED_REGISTER,
                value=2,
                timeout_seconds=0.1,
            )

    def test_fc06_rejects_modbus_exception(self) -> None:
        response = append_crc(bytes((44, 0x86, 0x02)))
        port = FakePort(response)

        with self.assertRaisesRegex(ModbusError, "exception 0x02"):
            write_single_register(
                port,
                slave_address=44,
                register_address=AERO_AIRING_REGISTER,
                value=1,
                timeout_seconds=0.1,
            )


if __name__ == "__main__":
    unittest.main()
