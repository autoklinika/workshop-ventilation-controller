import struct
import unittest

from ventilation_core.infrastructure.modbus_rtu import (
    ModbusError,
    append_crc,
    crc16_modbus,
    read_input_registers,
)


class FakePort:
    timeout = 0.1

    def __init__(self, response: bytes) -> None:
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


class ModbusRtuTests(unittest.TestCase):
    def test_known_crc(self) -> None:
        request_without_crc = bytes.fromhex("01 04 00 00 00 13")
        self.assertEqual(crc16_modbus(request_without_crc), 0xC7B1)
        self.assertEqual(append_crc(request_without_crc), bytes.fromhex("01 04 00 00 00 13 B1 C7"))

    def test_reads_input_registers(self) -> None:
        registers = list(range(19))
        payload = struct.pack(">19H", *registers)
        response = append_crc(bytes((1, 4, len(payload))) + payload)
        port = FakePort(response)

        received = read_input_registers(
            port,
            slave_address=1,
            start_address=0,
            quantity=19,
            timeout_seconds=0.1,
        )

        self.assertEqual(received, registers)
        self.assertEqual(port.written, bytes.fromhex("01 04 00 00 00 13 B1 C7"))
        self.assertEqual(port.input_resets, 1)
        self.assertTrue(port.flushed)

    def test_invalid_crc_is_rejected(self) -> None:
        payload = struct.pack(">H", 123)
        response = bytes((1, 4, len(payload))) + payload + b"\x00\x00"
        port = FakePort(response)

        with self.assertRaises(ModbusError):
            read_input_registers(
                port,
                slave_address=1,
                start_address=0,
                quantity=1,
                timeout_seconds=0.1,
            )


if __name__ == "__main__":
    unittest.main()
