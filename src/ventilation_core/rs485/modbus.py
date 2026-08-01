from __future__ import annotations

from dataclasses import dataclass


class ModbusError(RuntimeError):
    """Base error for Modbus RTU framing and protocol failures."""


class ModbusCRCError(ModbusError):
    """Raised when a Modbus RTU frame has an invalid CRC."""


@dataclass(frozen=True)
class ModbusExceptionResponse(ModbusError):
    slave: int
    function: int
    exception_code: int

    def __str__(self) -> str:
        return (
            f"Modbus exception from slave {self.slave}: "
            f"function 0x{self.function:02X}, code 0x{self.exception_code:02X}"
        )


def _validate_u8(name: str, value: int, *, minimum: int = 0) -> int:
    parsed = int(value)
    if not minimum <= parsed <= 0xFF:
        raise ValueError(f"{name} must be between {minimum} and 255")
    return parsed


def _validate_u16(name: str, value: int) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 0xFFFF:
        raise ValueError(f"{name} must be between 0 and 65535")
    return parsed


def crc16_modbus(payload: bytes) -> int:
    crc = 0xFFFF
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(payload: bytes) -> bytes:
    crc = crc16_modbus(payload)
    return payload + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def validate_crc(frame: bytes) -> None:
    if len(frame) < 4:
        raise ModbusError("Modbus RTU frame is too short")
    expected = crc16_modbus(frame[:-2])
    received = frame[-2] | (frame[-1] << 8)
    if received != expected:
        raise ModbusCRCError(
            f"Invalid Modbus CRC: received 0x{received:04X}, expected 0x{expected:04X}"
        )


def _build_read_registers_request(
    function: int,
    slave: int,
    address: int,
    count: int,
) -> bytes:
    if function not in {0x03, 0x04}:
        raise ValueError("read register function must be 0x03 or 0x04")
    slave_id = _validate_u8("slave", slave, minimum=1)
    register_address = _validate_u16("address", address)
    register_count = int(count)
    if not 1 <= register_count <= 125:
        raise ValueError("count must be between 1 and 125")
    payload = bytes(
        (
            slave_id,
            function,
            (register_address >> 8) & 0xFF,
            register_address & 0xFF,
            (register_count >> 8) & 0xFF,
            register_count & 0xFF,
        )
    )
    return append_crc(payload)


def build_read_holding_registers_request(
    slave: int,
    address: int,
    count: int,
) -> bytes:
    return _build_read_registers_request(0x03, slave, address, count)


def build_read_input_registers_request(
    slave: int,
    address: int,
    count: int,
) -> bytes:
    return _build_read_registers_request(0x04, slave, address, count)


def _parse_read_registers_response(
    frame: bytes,
    *,
    expected_slave: int,
    expected_count: int,
    expected_function: int,
) -> list[int]:
    validate_crc(frame)
    if frame[0] != expected_slave:
        raise ModbusError(
            f"Unexpected slave address {frame[0]}, expected {expected_slave}"
        )
    function = frame[1]
    if function == (expected_function | 0x80):
        if len(frame) != 5:
            raise ModbusError("Malformed Modbus exception response")
        raise ModbusExceptionResponse(frame[0], expected_function, frame[2])
    if function != expected_function:
        raise ModbusError(f"Unexpected Modbus function 0x{function:02X}")
    expected_bytes = int(expected_count) * 2
    if frame[2] != expected_bytes:
        raise ModbusError(
            f"Unexpected payload size {frame[2]}, expected {expected_bytes} bytes"
        )
    if len(frame) != 3 + expected_bytes + 2:
        raise ModbusError("Modbus response length does not match byte count")
    data = frame[3:-2]
    return [
        (data[index] << 8) | data[index + 1]
        for index in range(0, len(data), 2)
    ]


def parse_read_holding_registers_response(
    frame: bytes,
    *,
    expected_slave: int,
    expected_count: int,
) -> list[int]:
    return _parse_read_registers_response(
        frame,
        expected_slave=expected_slave,
        expected_count=expected_count,
        expected_function=0x03,
    )


def parse_read_input_registers_response(
    frame: bytes,
    *,
    expected_slave: int,
    expected_count: int,
) -> list[int]:
    return _parse_read_registers_response(
        frame,
        expected_slave=expected_slave,
        expected_count=expected_count,
        expected_function=0x04,
    )
