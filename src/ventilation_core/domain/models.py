from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class VentilationMode(StrEnum):
    STOP = "STOP"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class FanSetpoints:
    supply_voltage: float
    extract_voltage: float

    @classmethod
    def stopped(cls) -> "FanSetpoints":
        return cls(0.0, 0.0)


@dataclass(frozen=True)
class CoreState:
    mode: VentilationMode
    setpoints: FanSetpoints
    hardware_ready: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data
