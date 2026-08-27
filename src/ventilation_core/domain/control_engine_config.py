from __future__ import annotations

from dataclasses import dataclass, fields
from math import isfinite
from typing import Any, Mapping

from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1


_POLICY_NUMERIC_FIELDS = (
    "pm2_5_reference_ug_m3",
    "pm2_5_high_ug_m3",
    "pm2_5_max_ug_m3",
    "pm10_reference_ug_m3",
    "voc_boost_index",
    "voc_high_index",
    "voc_max_index",
    "nox_boost_index",
    "nox_high_index",
    "nox_max_index",
    "temperature_normal_above_celsius",
    "temperature_limiting_from_celsius",
    "temperature_minimum_from_celsius",
)

_TUNING_INTEGER_FIELDS = {
    "aero_normal_speed",
    "aero_boost_speed",
    "aero_high_speed",
    "aero_max_speed",
    "aero_sensor_fallback_speed",
}


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a JSON object")
    return value


def _optional_number(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric or null without type coercion")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _optional_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer or null without type coercion")
    return value


def _strict_keys(payload: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{field} contains unsupported fields: {', '.join(sorted(unknown))}")


def _tuning_from_dict(payload: Mapping[str, Any]) -> ShadowOutputTuning:
    allowed = {item.name for item in fields(ShadowOutputTuning)}
    _strict_keys(payload, allowed, "control_engine.policy.tuning")
    values: dict[str, Any] = {}
    for name in allowed:
        raw = payload.get(name)
        if name in _TUNING_INTEGER_FIELDS:
            values[name] = _optional_integer(raw, f"control_engine.policy.tuning.{name}")
        else:
            values[name] = _optional_number(raw, f"control_engine.policy.tuning.{name}")
    return ShadowOutputTuning(**values)


def _tuning_to_dict(tuning: ShadowOutputTuning) -> dict[str, Any]:
    return {item.name: getattr(tuning, item.name) for item in fields(ShadowOutputTuning)}


@dataclass(frozen=True)
class ControlEngineConfig:
    """Persistent configuration of the non-actuating Automation Control Engine.

    This contract intentionally contains no actuation-enable flag. Persistence and
    tuning must not be able to grant the SHADOW evaluator authority over DAC/AERO.
    """

    policy: ShadowPolicyV1 = ShadowPolicyV1()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != 1
        ):
            raise ValueError("unsupported control_engine schema_version")
        if not isinstance(self.policy, ShadowPolicyV1):
            raise ValueError("policy must be ShadowPolicyV1")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ControlEngineConfig":
        payload = _mapping(payload, "control_engine config")
        _strict_keys(payload, {"schema_version", "policy"}, "control_engine config")

        schema_version = payload.get("schema_version", 1)
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != 1
        ):
            raise ValueError("unsupported control_engine schema_version")

        policy_payload = _mapping(payload.get("policy"), "control_engine.policy")
        policy_allowed = {"version", "tuning", *_POLICY_NUMERIC_FIELDS}
        _strict_keys(policy_payload, set(policy_allowed), "control_engine.policy")

        version = policy_payload.get("version")
        if not isinstance(version, str) or not version.strip() or len(version) > 80:
            raise ValueError("control_engine.policy.version must be non-empty text up to 80 characters")

        tuning_payload = _mapping(policy_payload.get("tuning"), "control_engine.policy.tuning")
        tuning = _tuning_from_dict(tuning_payload)

        numeric: dict[str, float] = {}
        for name in _POLICY_NUMERIC_FIELDS:
            value = _optional_number(policy_payload.get(name), f"control_engine.policy.{name}")
            if value is None:
                raise ValueError(f"control_engine.policy.{name} must not be null")
            numeric[name] = value

        policy = ShadowPolicyV1(
            version=version,
            tuning=tuning,
            **numeric,
        )
        return cls(policy=policy, schema_version=schema_version)

    def to_dict(self) -> dict[str, Any]:
        policy_payload: dict[str, Any] = {
            "version": self.policy.version,
            "tuning": _tuning_to_dict(self.policy.tuning),
        }
        for name in _POLICY_NUMERIC_FIELDS:
            policy_payload[name] = getattr(self.policy, name)
        return {
            "schema_version": self.schema_version,
            "policy": policy_payload,
        }
