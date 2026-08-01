import unittest

from ventilation_core.rs485.modbus import (
    ModbusCRCError,
    ModbusExceptionResponse,
    append_crc,
    build_read_holding_registers_request,
    build_read_input_registers_request,
    crc16_modbus,
    parse_read_holding_registers_response,
    parse_read_input_registers_response,
)


class ModbusRTUTest(unittest.TestCase):
    def test_reference_crc(self) -> None:
        payload = bytes.fromhex("01 03 00 00 00 0A")
        self.assertEqual(crc16_modbus(payload), 0xCDC5)
        self.assertEqual(append_crc(payload).hex(), "01030000000ac5cd")

    def test_build_read_holding_request(self) -> None:
        self.assertEqual(
            build_read_holding_registers_request(1, 0x0010, 2).hex(),
            "010300100002c5ce",
        )

    def test_build_read_input_request(self) -> None:
        self.assertEqual(
            build_read_input_registers_request(1, 0x0010, 2).hex(),
            "010400100002700e",
        )

    def test_parse_read_holding_response(self) -> None:
        frame = append_crc(bytes.fromhex("01 03 04 00 0A 01 02"))
        self.assertEqual(
            parse_read_holding_registers_response(
                frame, expected_slave=1, expected_count=2
            ),
            [10, 258],
        )

    def test_parse_read_input_response(self) -> None:
        frame = append_crc(bytes.fromhex("01 04 02 12 34"))
        self.assertEqual(
            parse_read_input_registers_response(
                frame, expected_slave=1, expected_count=1
            ),
            [0x1234],
        )

    def test_crc_failure(self) -> None:
        frame = bytearray(append_crc(bytes.fromhex("01 03 02 00 0A")))
        frame[-1] ^= 0xFF
        with self.assertRaises(ModbusCRCError):
            parse_read_holding_registers_response(
                bytes(frame), expected_slave=1, expected_count=1
            )

    def test_exception_response(self) -> None:
        frame = append_crc(bytes.fromhex("01 83 02"))
        with self.assertRaises(ModbusExceptionResponse) as raised:
            parse_read_holding_registers_response(
                frame, expected_slave=1, expected_count=1
            )
        self.assertEqual(raised.exception.exception_code, 2)
