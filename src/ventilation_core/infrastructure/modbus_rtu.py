from __future__ import annotations

import struct
import time
from typing import Protocol


FUNCTION_READ_INPUT_REGISTERS = 0x04


class SerialPort(Protocol):
    timeout: float | None

    def reset_input_buffer(self) -> None: ...
    def write(self, data: bytes) -> int: ...
    def flush(self) -> None: ...
    def read(self, size: int) -> bytes: ...


class ModbusError(RuntimeError):
    """A malformed, incomplete or exceptional Modbus RTU response."""


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def append_crc(frame: bytes) -> bytes:
    crc = crc16_modbus(frame)
    return frame + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def verify_crc(frame: bytes) -> None:
    if len(frame) < 4:
        raise ModbusError(f"Modbus frame is too short: {frame.hex(' ')}")
    expected = crc16_modbus(frame[:-2])
    received = frame[-2] | (frame[-1] << 8)
    if received != expected:
        raise ModbusError(
            f"Invalid Modbus CRC: received=0x{received:04X}, expected=0x{expected:04X}"
        )


def _read_exact(port: SerialPort, size: int, timeout_seconds: float) -> bytes:
    deadline = time.monotonic() + timeout_seconds
    result = bytearray()
    while len(result) < size and time.monotonic() < deadline:
        chunk = port.read(size - len(result))
        if chunk:
            result.extend(chunk)
    return bytes(result)


def read_input_registers(
    port: SerialPort,
    slave_address: int,
    start_address: int,
    quantity: int,
    timeout_seconds: float,
) -> list[int]:
    if not 1 <= slave_address <= 247:
        raise ValueError("Modbus slave address must be in range 1..247")
    if not 1 <= quantity <= 125:
        raise ValueError("Modbus register quantity must be in range 1..125")
    if timeout_seconds <= 0:
        raise ValueError("Modbus timeout must be positive")

    request = append_crc(
        struct.pack(
            ">BBHH",
            slave_address,
            FUNCTION_READ_INPUT_REGISTERS,
            start_address,
            quantity,
        )
    )
    port.reset_input_buffer()
    written = port.write(request)
    if written != len(request):
        raise ModbusError(f"Incomplete Modbus request write: {written}/{len(request)} bytes")
    port.flush()

    header = _read_exact(port, 3, timeout_seconds)
    if len(header) != 3:
        raise ModbusError("No response or incomplete Modbus header")

    response_address, function, third = header
    if response_address != slave_address:
        raise ModbusError(
            f"Unexpected slave address {response_address}; expected {slave_address}"
        )

    if function == (FUNCTION_READ_INPUT_REGISTERS | 0x80):
        tail = _read_exact(port, 2, timeout_seconds)
        frame = header + tail
        if len(frame) != 5:
            raise ModbusError("Incomplete Modbus exception response")
        verify_crc(frame)
        raise ModbusError(f"Modbus exception 0x{third:02X}")

    if function != FUNCTION_READ_INPUT_REGISTERS:
        raise ModbusError(f"Unexpected Modbus function 0x{function:02X}")

    expected_byte_count = quantity * 2
    if third != expected_byte_count:
        raise ModbusError(
            f"Unexpected payload length {third}; expected {expected_byte_count}"
        )

    tail = _read_exact(port, third + 2, timeout_seconds)
    frame = header + tail
    if len(frame) != 3 + third + 2:
        raise ModbusError("Incomplete Modbus response")
    verify_crc(frame)
    return list(struct.unpack(f">{quantity}H", frame[3:-2]))
