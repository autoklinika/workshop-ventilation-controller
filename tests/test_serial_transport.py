import unittest

from ventilation_core.rs485.modbus import append_crc
from ventilation_core.rs485.serial_transport import (
    PySerialModbusTransport,
    SerialSettings,
    SerialTransportError,
)


class FakeSerial:
    def __init__(self, response: bytes) -> None:
        self.response = bytearray(response)
        self.written = bytearray()
        self.closed = False
        self.input_resets = 0
        self.output_resets = 0

    def reset_input_buffer(self) -> None:
        self.input_resets += 1

    def reset_output_buffer(self) -> None:
        self.output_resets += 1

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        return len(data)

    def flush(self) -> None:
        pass

    def read(self, size: int = 1) -> bytes:
        data = bytes(self.response[:size])
        del self.response[:size]
        return data

    def close(self) -> None:
        self.closed = True


class SerialTransportTest(unittest.TestCase):
    def test_transaction_reads_variable_length_response(self) -> None:
        response = append_crc(bytes.fromhex("01 03 02 12 34"))
        serial = FakeSerial(response)
        transport = PySerialModbusTransport(
            SerialSettings("/dev/fake"), serial_instance=serial
        )
        request = bytes.fromhex("01 03 00 00 00 01 84 0A")
        self.assertEqual(transport.transact(request), response)
        self.assertEqual(bytes(serial.written), request)

    def test_timeout_is_reported(self) -> None:
        serial = FakeSerial(b"")
        transport = PySerialModbusTransport(
            SerialSettings("/dev/fake"), serial_instance=serial
        )
        with self.assertRaises(SerialTransportError):
            transport.transact(b"1234")

    def test_raw_write_and_synchronized_exact_read(self) -> None:
        payload = bytes.fromhex("57 56 43 32 2D 52 53 34 38 35")
        serial = FakeSerial(payload)
        transport = PySerialModbusTransport(
            SerialSettings("/dev/fake"), serial_instance=serial
        )

        transport.clear_input()
        self.assertEqual(transport.write_raw(payload), len(payload))
        self.assertEqual(
            transport.read_exact(len(payload), clear_buffer=False),
            payload,
        )
        self.assertEqual(bytes(serial.written), payload)
        self.assertEqual(serial.output_resets, 1)
        self.assertEqual(serial.input_resets, 1)

    def test_raw_read_clears_input_by_default(self) -> None:
        payload = b"abcd"
        serial = FakeSerial(payload)
        transport = PySerialModbusTransport(
            SerialSettings("/dev/fake"), serial_instance=serial
        )

        self.assertEqual(transport.read_exact(len(payload)), payload)
        self.assertEqual(serial.input_resets, 1)

    def test_raw_empty_payload_is_rejected(self) -> None:
        transport = PySerialModbusTransport(
            SerialSettings("/dev/fake"), serial_instance=FakeSerial(b"")
        )
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            transport.write_raw(b"")
