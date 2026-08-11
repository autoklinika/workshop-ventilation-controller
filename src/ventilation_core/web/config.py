from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WebUiConfig:
    zone1_name: str = "Mycie i wygrzewanie ECU"
    zone1_sensor_address: int = 1
    zone2_name: str = "Pomieszczenie lutowania"
    zone2_sensor_address: int = 2

    def __post_init__(self) -> None:
        for name, value in (
            ("zone1_sensor_address", self.zone1_sensor_address),
            ("zone2_sensor_address", self.zone2_sensor_address),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 247:
                raise ValueError(f"{name} must be a Modbus address within 1..247")
        if self.zone1_sensor_address == self.zone2_sensor_address:
            raise ValueError("Zone sensor addresses must be different")
        if not self.zone1_name.strip() or not self.zone2_name.strip():
            raise ValueError("Zone display names must not be empty")

    @classmethod
    def from_environment(cls) -> "WebUiConfig":
        return cls(
            zone1_name=os.getenv("WVC_WEB_ZONE1_NAME", cls.zone1_name),
            zone1_sensor_address=int(
                os.getenv("WVC_WEB_ZONE1_SENSOR_ADDRESS", str(cls.zone1_sensor_address))
            ),
            zone2_name=os.getenv("WVC_WEB_ZONE2_NAME", cls.zone2_name),
            zone2_sensor_address=int(
                os.getenv("WVC_WEB_ZONE2_SENSOR_ADDRESS", str(cls.zone2_sensor_address))
            ),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "zone1": {
                "name": self.zone1_name,
                "sensor_address": self.zone1_sensor_address,
                "actuator": "dac_ec_fans",
            },
            "zone2": {
                "name": self.zone2_name,
                "sensor_address": self.zone2_sensor_address,
                "actuator": "aero",
            },
            "manual_control_only": True,
            "automation_enabled": False,
            "ai_control_enabled": False,
        }
