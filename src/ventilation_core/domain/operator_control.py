from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any, Mapping


class OperatorMode(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


_OPERATOR_KEYS = {
    "mode",
    "manual_supply_pct",
    "manual_extract_pct",
    "manual_aero_speed",
}
_MANUAL_KEYS = {
    "manual_supply_pct",
    "manual_extract_pct",
    "manual_aero_speed",
}


def _percentage(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric without type coercion")
    result = float(value)
    if not isfinite(result) or not 0.0 <= result <= 100.0:
        raise ValueError(f"{field} must be finite and within 0..100")
    return result


def _aero_speed(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in {0, 1, 2, 3}:
        raise ValueError(f"{field} must be an integer in 0..3")
    return value


@dataclass(frozen=True)
class OperatorControlIntent:
    """Volatile operator request owned by ventilation-core.

    The intent is deliberately not a physical actuator command. MANUAL values are
    percentages / logical AERO speed consumed only by the Control Engine SHADOW
    layer. A core restart starts from AUTO so a stale manual override cannot revive
    without a new explicit operator action.
    """

    mode: OperatorMode = OperatorMode.AUTO
    manual_supply_pct: float | None = None
    manual_extract_pct: float | None = None
    manual_aero_speed: int | None = None

    def __post_init__(self) -> None:
        if self.mode == OperatorMode.AUTO:
            if any(
                value is not None
                for value in (
                    self.manual_supply_pct,
                    self.manual_extract_pct,
                    self.manual_aero_speed,
                )
            ):
                raise ValueError("AUTO operator intent must not contain MANUAL setpoints")
            return

        if self.mode != OperatorMode.MANUAL:
            raise ValueError(f"Unsupported operator mode: {self.mode}")
        if self.manual_supply_pct is None or self.manual_extract_pct is None:
            raise ValueError("MANUAL operator intent requires supply and extract percentages")
        if self.manual_aero_speed is None:
            raise ValueError("MANUAL operator intent requires an AERO speed")
        _percentage(self.manual_supply_pct, "manual_supply_pct")
        _percentage(self.manual_extract_pct, "manual_extract_pct")
        _aero_speed(self.manual_aero_speed, "manual_aero_speed")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OperatorControlIntent":
        if not isinstance(payload, Mapping):
            raise ValueError("operator intent must be a JSON object")
        unknown = set(payload) - _OPERATOR_KEYS
        if unknown:
            raise ValueError(
                "operator intent contains unsupported fields: "
                + ", ".join(sorted(unknown))
            )

        raw_mode = payload.get("mode")
        if not isinstance(raw_mode, str):
            raise ValueError("operator mode must be AUTO or MANUAL")
        try:
            mode = OperatorMode(raw_mode)
        except ValueError as exc:
            raise ValueError("operator mode must be AUTO or MANUAL") from exc

        if mode == OperatorMode.AUTO:
            supplied_manual_fields = sorted(_MANUAL_KEYS & set(payload))
            if supplied_manual_fields:
                raise ValueError(
                    "AUTO operator intent must not contain MANUAL fields: "
                    + ", ".join(supplied_manual_fields)
                )
            return cls(mode=mode)

        missing = [field for field in sorted(_MANUAL_KEYS) if field not in payload]
        if missing:
            raise ValueError("MANUAL operator intent missing fields: " + ", ".join(missing))
        return cls(
            mode=mode,
            manual_supply_pct=_percentage(payload["manual_supply_pct"], "manual_supply_pct"),
            manual_extract_pct=_percentage(payload["manual_extract_pct"], "manual_extract_pct"),
            manual_aero_speed=_aero_speed(payload["manual_aero_speed"], "manual_aero_speed"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "manual_supply_pct": self.manual_supply_pct,
            "manual_extract_pct": self.manual_extract_pct,
            "manual_aero_speed": self.manual_aero_speed,
        }
