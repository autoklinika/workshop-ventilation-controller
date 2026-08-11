from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from ventilation_core.domain.aero_control import (
    AERO_CONFIRMATION_POLL_INTERVAL_SECONDS,
    AERO_EXECUTION_TIMEOUT_SECONDS,
    AeroControlCommand,
    AeroControlExecutionState,
    AeroControlResult,
    AeroFanPower,
)
from ventilation_core.infrastructure.modbus_rtu import (
    ModbusError,
    read_holding_registers,
    write_single_register,
)


FAN_1_REGISTER = 2033
FAN_2_REGISTER = 2034


@dataclass(frozen=True)
class AeroControlExecutorConfig:
    slave_address: int = 44
    timeout_seconds: float = 0.5
    execution_timeout_seconds: float = AERO_EXECUTION_TIMEOUT_SECONDS
    confirmation_poll_interval_seconds: float = AERO_CONFIRMATION_POLL_INTERVAL_SECONDS


def _read_one(port: Any, config: AeroControlExecutorConfig, address: int) -> int:
    return read_holding_registers(
        port,
        slave_address=config.slave_address,
        start_address=address,
        quantity=1,
        timeout_seconds=config.timeout_seconds,
    )[0]


def _read_fan_power(port: Any, config: AeroControlExecutorConfig) -> AeroFanPower:
    return AeroFanPower(
        fan_1_percent=_read_one(port, config, FAN_1_REGISTER),
        fan_2_percent=_read_one(port, config, FAN_2_REGISTER),
    )


def _restore_previous(
    port: Any,
    config: AeroControlExecutorConfig,
    command: AeroControlCommand,
    previous: int,
) -> bool:
    try:
        write_single_register(
            port,
            slave_address=config.slave_address,
            register_address=command.register_address,
            value=previous,
            timeout_seconds=config.timeout_seconds,
        )
        return _read_one(port, config, command.register_address) == previous
    except (ModbusError, ValueError):
        return False


def execute_control_change(
    port: Any,
    config: AeroControlExecutorConfig,
    command: AeroControlCommand,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> AeroControlResult:
    """Execute one guarded AERO command with protocol and physical confirmation.

    This function does not own a UART and must only be called by the AERO BUS owner.
    On failed physical confirmation it restores the previous control register value.
    """

    previous = _read_one(port, config, command.register_address)
    baseline = _read_fan_power(port, config)

    if previous == command.value:
        return AeroControlResult(
            command=command,
            state=AeroControlExecutionState.SUCCEEDED,
            previous_value=previous,
            readback_value=previous,
            baseline_power=baseline,
            observed_power=baseline,
            recovered=True,
            physical_confirmation=True,
        )

    try:
        write_single_register(
            port,
            slave_address=config.slave_address,
            register_address=command.register_address,
            value=command.value,
            timeout_seconds=config.timeout_seconds,
        )
        readback = _read_one(port, config, command.register_address)
        if readback != command.value:
            raise ModbusError(
                f"AERO control readback mismatch: got {readback}, expected {command.value}"
            )
    except (ModbusError, ValueError) as exc:
        recovered = _restore_previous(port, config, command, previous)
        return AeroControlResult(
            command=command,
            state=AeroControlExecutionState.FAILED,
            previous_value=previous,
            baseline_power=baseline,
            recovered=recovered,
            error=str(exc),
        )

    deadline = monotonic() + config.execution_timeout_seconds
    observed = baseline
    while monotonic() < deadline:
        sleep(config.confirmation_poll_interval_seconds)
        observed = _read_fan_power(port, config)
        if observed != baseline:
            return AeroControlResult(
                command=command,
                state=AeroControlExecutionState.SUCCEEDED,
                previous_value=previous,
                readback_value=readback,
                baseline_power=baseline,
                observed_power=observed,
                physical_confirmation=True,
            )

    recovered = _restore_previous(port, config, command, previous)
    return AeroControlResult(
        command=command,
        state=AeroControlExecutionState.FAILED,
        previous_value=previous,
        readback_value=readback,
        baseline_power=baseline,
        observed_power=observed,
        recovered=recovered,
        physical_confirmation=False,
        error=(
            "AERO physical response was not confirmed within "
            f"{config.execution_timeout_seconds:.1f} s"
        ),
    )
