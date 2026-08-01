"""RS-485 / Modbus RTU bring-up infrastructure."""

from .modbus import (
    ModbusCRCError,
    ModbusError,
    ModbusExceptionResponse,
    append_crc,
    build_read_holding_registers_request,
    build_read_input_registers_request,
    crc16_modbus,
    parse_read_holding_registers_response,
    parse_read_input_registers_response,
)

__all__ = [
    "ModbusCRCError",
    "ModbusError",
    "ModbusExceptionResponse",
    "append_crc",
    "build_read_holding_registers_request",
    "build_read_input_registers_request",
    "crc16_modbus",
    "parse_read_holding_registers_response",
    "parse_read_input_registers_response",
]
