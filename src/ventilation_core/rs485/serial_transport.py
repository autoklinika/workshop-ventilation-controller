from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .modbus import ModbusError


class SerialLike(Protocol):
    def reset_input_buffer(self) -> None: ...
    def reset_output_buffer(self) -> None: ...
    def write(self, data: bytes) -> int: ...
    def flush(self) -> None: ...
    def read(self, size: int = 1) -> bytes: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class SerialSettings:
    port: str
    baudrate: int = 9600
    parity: str = "N"
    stopbits: int = 1
    bytesize: int = 8
    timeout_seconds: float = 0.5

    def __post_init__(self) -> None:
        if not self.port:
            raise ValueError("RS-485 port cannot be empty")
        if self.baudrate <= 0:
            raise ValueError("RS-485 baudrate must be positive")
        if self.parity.upper() not in {"N", "E", "O"}:
            raise ValueError("RS-485 parity must be N, E or O")
        if self.stopbits not in {1, 2}:
            raise ValueError("RS-485 stopbits must be 1 or 2")
        if self.bytesize not in {7, 8}:
            raise ValueError("RS-485 bytesize must be 7 or 8")
        if self.timeout_seconds <= 0:
            raise ValueError("RS-485 timeout must be positive")


class SerialTransportError(ModbusError):
    pass


def _read_exact(serial_port: SerialLike, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = serial_port.read(size - len(data))
        if not chunk:
            raise SerialTransportError(
                f"RS-485 response timed out after {len(data)} of {size} bytes"
            )
        data.extend(chunk)
    return bytes(data)


def read_modbus_rtu_frame(serial_port: SerialLike) -> bytes:
    header = _read_exact(serial_port, 2)
    function = header[1]
    if function & 0x80:
        return header + _read_exact(serial_port, 3)
    if function in {0x01, 0x02, 0x03, 0x04}:
        byte_count = _read_exact(serial_port, 1)
        return header + byte_count + _read_exact(serial_port, byte_count[0] + 2)
    if function in {0x05, 0x06, 0x0F, 0x10}:
        return header + _read_exact(serial_port, 6)
    raise SerialTransportError(
        f"Unsupported Modbus response function 0x{function:02X} during bring-up"
    )


class PySerialModbusTransport:
    """Owns one serial port and performs synchronous Modbus RTU transactions."""

    def __init__(
        self,
        settings: SerialSettings,
        *,
        serial_instance: SerialLike | None = None,
    ) -> None:
        self.settings = settings
        if serial_instance is not None:
            self._serial = serial_instance
            return
        try:
            import serial
        except ImportError as exc:
            raise SerialTransportError(
                "pyserial is missing. Install: sudo apt install python3-serial"
            ) from exc
        try:
            self._serial = serial.Serial(
                port=settings.port,
                baudrate=settings.baudrate,
                bytesize=settings.bytesize,
                parity=settings.parity.upper(),
                stopbits=settings.stopbits,
                timeout=settings.timeout_seconds,
                inter_byte_timeout=settings.timeout_seconds,
            )
        except Exception as exc:
            raise SerialTransportError(
                f"Cannot open RS-485 port {settings.port}: {exc}"
            ) from exc

    def transact(self, request: bytes) -> bytes:
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        written = self._serial.write(request)
        if written != len(request):
            raise SerialTransportError(
                f"Short RS-485 write: {written} of {len(request)} bytes"
            )
        self._serial.flush()
        return read_modbus_rtu_frame(self._serial)

    def close(self) -> None:
        self._serial.close()
