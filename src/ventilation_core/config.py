from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CoreConfig:
    i2c_bus: int = 1
    i2c_address: int = 0x58
    socket_path: Path = Path("/run/workshop-ventilation/ventilation-core.sock")
    minimum_running_voltage: float = 1.0
    maximum_voltage: float = 10.0
    command_timeout_seconds: float = 3.0
    worker_health_interval_seconds: float = 1.0
