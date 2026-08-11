from __future__ import annotations

import struct
import time
from typing import Protocol


FUNCTION_READ_HOLDING_REGISTERS = 0x03
FUNCTION_READ_INPUT_REGISTERS = 0x04
FUNCTION_WRITE_SINGLE_REGISTER = 0x06


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


def _validate_common_request(
    *,
    slave_address: int,
    register_address: int,
    timeout_seconds: float,
) -> None:
    if not 1 <= slave_address <= 247:
        raise ValueError("Modbus slave address must be in range 1..247")
    if not 0 <= register_address <= 0xFFFF:
        raise ValueError("Modbus register address must be in range 0..65535")
    if timeout_seconds <= 0:
        raise ValueError("Modbus timeout must be positive")


def _read_registers(
    port: SerialPort,
    *,
    function_code: int,
    slave_address: int,
    start_address: int,
    quantity: int,
    timeout_seconds: float,
) -> list[int]:
    if function_code not in (
        FUNCTION_READ_HOLDING_REGISTERS,
        FUNCTION_READ_INPUT_REGISTERS,
    ):
        raise ValueError(f"Unsupported Modbus read function 0x{function_code:02X}")
    _validate_common_request(
        slave_address=slave_address,
        register_address=start_address,
        timeout_seconds=timeout_seconds,
    )
    if not 1 <= quantity <= 125:
        raise ValueError("Modbus register quantity must be in range 1..125")
    if start_address + quantity > 0x10000:
        raise ValueError("Modbus register range exceeds address space")

    request = append_crc(
        struct.pack(
            ">BBHH",
            slave_address,
            function_code,
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

    if function == (function_code | 0x80):
        tail = _read_exact(port, 2, timeout_seconds)
        frame = header + tail
        if len(frame) != 5:
            raise ModbusError("Incomplete Modbus exception response")
        verify_crc(frame)
        raise ModbusError(f"Modbus exception 0x{third:02X}")

    if function != function_code:
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


def read_holding_registers(
    port: SerialPort,
    slave_address: int,
    start_address: int,
    quantity: int,
    timeout_seconds: float,
) -> list[int]:
    return _read_registers(
        port,
        function_code=FUNCTION_READ_HOLDING_REGISTERS,
        slave_address=slave_address,
        start_address=start_address,
        quantity=quantity,
        timeout_seconds=timeout_seconds,
    )


def read_input_registers(
    port: SerialPort,
    slave_address: int,
    start_address: int,
    quantity: int,
    timeout_seconds: float,
) -> list[int]:
    return _read_registers(
        port,
        function_code=FUNCTION_READ_INPUT_REGISTERS,
        slave_address=slave_address,
        start_address=start_address,
        quantity=quantity,
        timeout_seconds=timeout_seconds,
    )


def write_single_register(
    port: SerialPort,
    *,
    slave_address: int,
    register_address: int,
    value: int,
    timeout_seconds: float,
) -> None:
    """Write one holding register with FC06 and require an exact protocol echo."""

    _validate_common_request(
        slave_address=slave_address,
        register_address=register_address,
        timeout_seconds=timeout_seconds,
    )
    if not 0 <= value <= 0xFFFF:
        raise ValueError("Modbus register value must be in range 0..65535")

    request_without_crc = struct.pack(
        ">BBHH",
        slave_address,
        FUNCTION_WRITE_SINGLE_REGISTER,
        register_address,
        value,
    )
    request = append_crc(request_without_crc)

    port.reset_input_buffer()
    written = port.write(request)
    if written != len(request):
        raise ModbusError(f"Incomplete Modbus request write: {written}/{len(request)} bytes")
    port.flush()

    header = _read_exact(port, 2, timeout_seconds)
    if len(header) != 2:
        raise ModbusError("No response or incomplete Modbus write header")

    response_address, function = header
    if response_address != slave_address:
        raise ModbusError(
            f"Unexpected slave address {response_address}; expected {slave_address}"
        )

    if function == (FUNCTION_WRITE_SINGLE_REGISTER | 0x80):
        tail = _read_exact(port, 3, timeout_seconds)
        frame = header + tail
        if len(frame) != 5:
            raise ModbusError("Incomplete Modbus exception response")
        verify_crc(frame)
        raise ModbusError(f"Modbus exception 0x{frame[2]:02X}")

    if function != FUNCTION_WRITE_SINGLE_REGISTER:
        raise ModbusError(f"Unexpected Modbus function 0x{function:02X}")

    tail = _read_exact(port, 6, timeout_seconds)
    frame = header + tail
    if len(frame) != 8:
        raise ModbusError("Incomplete Modbus FC06 echo response")
    verify_crc(frame)

    if frame != request:
        echoed_register, echoed_value = struct.unpack(">HH", frame[2:6])
        raise ModbusError(
            "FC06 echo mismatch: "
            f"register={echoed_register} value={echoed_value}; "
            f"expected register={register_address} value={value}"
        )
