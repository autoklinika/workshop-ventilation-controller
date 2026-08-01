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

    def reset_input_buffer(self) -> None:
        pass

    def reset_output_buffer(self) -> None:
        pass

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
