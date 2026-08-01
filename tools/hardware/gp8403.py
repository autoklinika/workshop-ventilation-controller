#!/usr/bin/env python3
"""Minimal GP8403/DFR0971 driver for Raspberry Pi hardware bring-up.

The implementation intentionally does not expose the non-volatile ``store``
operation. During bring-up we do not want a non-zero DAC value restored after
a power cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SMBusLike(Protocol):
    def read_byte(self, address: int) -> int: ...
    def write_word_data(self, address: int, register: int, value: int) -> None: ...
    def close(self) -> None: ...


class GP8403Error(RuntimeError):
    """Raised when the DAC cannot be accessed or receives invalid input."""


@dataclass(frozen=True)
class GP8403Config:
    bus: int = 1
    address: int = 0x58
    output_range_volts: float = 10.0


class GP8403:
    """Small, dependency-light driver for the DFRobot DFR0971 (GP8403)."""

    RANGE_REGISTER = 0x01
    CHANNEL_REGISTERS = {0: 0x02, 1: 0x04}
    RANGE_5V = 0x0000
    RANGE_10V = 0x0011
    MAX_CODE = 0x0FFF

    def __init__(
        self,
        config: GP8403Config = GP8403Config(),
        *,
        bus_instance: SMBusLike | None = None,
    ) -> None:
        if not 0x03 <= config.address <= 0x77:
            raise ValueError(f"Invalid 7-bit I2C address: 0x{config.address:02X}")
        if config.output_range_volts not in (5.0, 10.0):
            raise ValueError("Output range must be 5.0 or 10.0 volts")

        self.config = config
        self._owns_bus = bus_instance is None

        if bus_instance is not None:
            self._bus = bus_instance
        else:
            try:
                from smbus import SMBus
            except ImportError as exc:
                raise GP8403Error(
                    "Python SMBus module is missing. Install package: "
                    "sudo apt install python3-smbus"
                ) from exc
            try:
                self._bus = SMBus(config.bus)
            except OSError as exc:
                raise GP8403Error(
                    f"Cannot open I2C bus /dev/i2c-{config.bus}: {exc}"
                ) from exc

    def __enter__(self) -> "GP8403":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_bus:
            self._bus.close()

    def probe(self) -> int:
        """Confirm that the device acknowledges and return its read byte."""
        try:
            return self._bus.read_byte(self.config.address)
        except OSError as exc:
            raise GP8403Error(
                f"No response from GP8403 at 0x{self.config.address:02X} "
                f"on I2C bus {self.config.bus}: {exc}"
            ) from exc

    def configure_output_range(self) -> None:
        value = self.RANGE_10V if self.config.output_range_volts == 10.0 else self.RANGE_5V
        self._write_word(self.RANGE_REGISTER, value)

    def voltage_to_word(self, voltage: float) -> int:
        if not 0.0 <= voltage <= self.config.output_range_volts:
            raise ValueError(
                f"Voltage must be between 0.0 and "
                f"{self.config.output_range_volts:.1f} V"
            )
        code = round((voltage / self.config.output_range_volts) * self.MAX_CODE)
        code = min(max(code, 0), self.MAX_CODE)
        return code << 4

    def set_voltage(self, channel: int, voltage: float) -> None:
        if channel not in self.CHANNEL_REGISTERS:
            raise ValueError("Channel must be 0 or 1")
        self._write_word(
            self.CHANNEL_REGISTERS[channel],
            self.voltage_to_word(voltage),
        )

    def set_both(self, voltage: float) -> None:
        self.set_voltage(0, voltage)
        self.set_voltage(1, voltage)

    def zero_all(self) -> None:
        self.set_both(0.0)

    def _write_word(self, register: int, value: int) -> None:
        try:
            self._bus.write_word_data(self.config.address, register, value)
        except OSError as exc:
            raise GP8403Error(
                f"I2C write failed at address 0x{self.config.address:02X}, "
                f"register 0x{register:02X}: {exc}"
            ) from exc
