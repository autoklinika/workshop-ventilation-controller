from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


AERO_SPEED_REGISTER = 1080
AERO_AIRING_REGISTER = 1081
AERO_EXECUTION_TIMEOUT_SECONDS = 60.0
AERO_CONFIRMATION_POLL_INTERVAL_SECONDS = 2.0


class AeroControlKind(StrEnum):
    SPEED = "speed"
    AIRING = "airing"


class AeroControlExecutionState(StrEnum):
    IDLE = "idle"
    WRITE_PENDING = "write_pending"
    WAITING_READBACK = "waiting_readback"
    WAITING_PHYSICAL_CONFIRMATION = "waiting_physical_confirmation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RECOVERY_PENDING = "recovery_pending"


@dataclass(frozen=True)
class AeroControlCommand:
    kind: AeroControlKind
    register_address: int
    value: int

    def __post_init__(self) -> None:
        if self.kind is AeroControlKind.SPEED:
            if self.register_address != AERO_SPEED_REGISTER:
                raise ValueError("AERO speed command must target register 1080")
            if self.value not in (0, 1, 2, 3):
                raise ValueError("AERO speed must be one of 0, 1, 2, 3")
            return

        if self.kind is AeroControlKind.AIRING:
            if self.register_address != AERO_AIRING_REGISTER:
                raise ValueError("AERO airing command must target register 1081")
            if self.value not in (0, 1):
                raise ValueError("AERO airing value must be 0 or 1")
            return

        raise ValueError(f"Unsupported AERO control kind: {self.kind}")

    @classmethod
    def set_speed(cls, speed: int) -> "AeroControlCommand":
        return cls(AeroControlKind.SPEED, AERO_SPEED_REGISTER, speed)

    @classmethod
    def set_airing(cls, enabled: bool) -> "AeroControlCommand":
        return cls(AeroControlKind.AIRING, AERO_AIRING_REGISTER, int(enabled))


@dataclass(frozen=True)
class AeroFanPower:
    fan_1_percent: int
    fan_2_percent: int

    def __post_init__(self) -> None:
        if not 0 <= self.fan_1_percent <= 100:
            raise ValueError("AERO fan_1 power must be in range 0..100")
        if not 0 <= self.fan_2_percent <= 100:
            raise ValueError("AERO fan_2 power must be in range 0..100")

    def to_dict(self) -> dict[str, int]:
        return {
            "fan_1_percent": self.fan_1_percent,
            "fan_2_percent": self.fan_2_percent,
        }


@dataclass(frozen=True)
class AeroControlResult:
    command: AeroControlCommand
    state: AeroControlExecutionState
    previous_value: int | None = None
    readback_value: int | None = None
    baseline_power: AeroFanPower | None = None
    observed_power: AeroFanPower | None = None
    recovered: bool = False
    physical_confirmation: bool = False
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.state is AeroControlExecutionState.SUCCEEDED

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.command.kind.value,
            "register_address": self.command.register_address,
            "target_value": self.command.value,
            "state": self.state.value,
            "previous_value": self.previous_value,
            "readback_value": self.readback_value,
            "baseline_power": (
                None if self.baseline_power is None else self.baseline_power.to_dict()
            ),
            "observed_power": (
                None if self.observed_power is None else self.observed_power.to_dict()
            ),
            "recovered": self.recovered,
            "physical_confirmation": self.physical_confirmation,
            "error": self.error,
        }
