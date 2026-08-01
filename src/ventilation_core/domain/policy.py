from __future__ import annotations

from dataclasses import dataclass

from .models import FanSetpoints


class SetpointValidationError(ValueError):
    """Raised when a fan setpoint violates an operational safety rule."""


@dataclass(frozen=True)
class FanSetpointPolicy:
    minimum_running_voltage: float = 1.0
    maximum_voltage: float = 10.0

    def validate_voltage(self, voltage: float) -> float:
        value = float(voltage)
        if value == 0.0:
            return 0.0
        if self.minimum_running_voltage <= value <= self.maximum_voltage:
            return value
        raise SetpointValidationError(
            "Fan voltage must be 0 V (stop) or between "
            f"{self.minimum_running_voltage:.1f} V and {self.maximum_voltage:.1f} V"
        )

    def validate(self, setpoints: FanSetpoints) -> FanSetpoints:
        return FanSetpoints(
            supply_voltage=self.validate_voltage(setpoints.supply_voltage),
            extract_voltage=self.validate_voltage(setpoints.extract_voltage),
        )
