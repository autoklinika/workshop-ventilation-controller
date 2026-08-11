from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
