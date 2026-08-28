from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ventilation_core.domain.shadow_policy import ShadowOutputTuning
from ventilation_core.domain.tuning_validation import (
    TUNING_GROUP_REQUIREMENTS,
    ValidationLevel,
)


GROUP_FIELDS: dict[str, tuple[str, ...]] = {
    "fan_outputs": (
        "normal_air_request_pct",
        "boost_air_request_pct",
        "high_air_request_pct",
        "max_air_request_pct",
        "thermal_normal_limit_pct",
        "thermal_limiting_limit_pct",
        "thermal_minimum_limit_pct",
        "thermal_protection_limit_pct",
        "extract_bias_pct",
    ),
    "aero_outputs": (
        "aero_normal_speed",
        "aero_boost_speed",
        "aero_high_speed",
        "aero_max_speed",
    ),
    "dynamics": (
        "pm2_5_hysteresis_ug_m3",
        "voc_hysteresis_index",
        "nox_hysteresis_index",
        "temperature_hysteresis_celsius",
        "pm2_5_boost_confirmation_seconds",
        "state_minimum_hold_seconds",
        "boost_decay_seconds",
    ),
    "fan_sensor_fallback": (
        "sensor_fallback_supply_pct",
        "sensor_fallback_extract_pct",
    ),
    "aero_sensor_fallback": ("aero_sensor_fallback_speed",),
    "tacho_confirmation": ("tacho_failure_confirmation_seconds",),
    "tacho_supply_fallback": (
        "tacho_supply_fault_fallback_supply_pct",
        "tacho_supply_fault_fallback_extract_pct",
    ),
    "tacho_extract_fallback": (
        "tacho_extract_fault_fallback_supply_pct",
        "tacho_extract_fault_fallback_extract_pct",
    ),
    "tacho_both_fallback": (
        "tacho_both_fault_fallback_supply_pct",
        "tacho_both_fault_fallback_extract_pct",
    ),
}

if set(GROUP_FIELDS) != set(TUNING_GROUP_REQUIREMENTS):
    raise RuntimeError("commissioning candidate groups drifted from validation requirements")


@dataclass(frozen=True)
class CommissioningCandidateGroup:
    level: ValidationLevel
    values: tuple[tuple[str, int | float | None], ...]
    evidence: tuple[str, ...]
    note: str | None = None

    @classmethod
    def from_dict(
        cls,
        name: str,
        payload: Mapping[str, Any],
    ) -> "CommissioningCandidateGroup":
        if not isinstance(payload, Mapping):
            raise ValueError(f"candidate group {name} must be a JSON object")
        unknown = set(payload) - {"level", "values", "evidence", "note"}
        if unknown:
            raise ValueError(
                f"candidate group {name} contains unsupported fields: {', '.join(sorted(unknown))}"
            )
        level = ValidationLevel.from_name(payload.get("level", "UNVALIDATED"))
        raw_values = payload.get("values")
        if not isinstance(raw_values, Mapping):
            raise ValueError(f"candidate group {name}.values must be a JSON object")
        expected_fields = set(GROUP_FIELDS[name])
        if set(raw_values) != expected_fields:
            missing = expected_fields - set(raw_values)
            extra = set(raw_values) - expected_fields
            details = []
            if missing:
                details.append(f"missing={','.join(sorted(missing))}")
            if extra:
                details.append(f"unsupported={','.join(sorted(extra))}")
            raise ValueError(f"candidate group {name} field mismatch: {'; '.join(details)}")
        values: list[tuple[str, int | float | None]] = []
        for field in GROUP_FIELDS[name]:
            value = raw_values[field]
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError(f"candidate {name}.{field} must be numeric or null")
            values.append((field, value))
        raw_evidence = payload.get("evidence", [])
        if not isinstance(raw_evidence, list) or any(
            not isinstance(item, str) or not item.strip() for item in raw_evidence
        ):
            raise ValueError(f"candidate group {name}.evidence must be an array of non-empty strings")
        note = payload.get("note")
        if note is not None and (not isinstance(note, str) or not note.strip()):
            raise ValueError(f"candidate group {name}.note must be non-empty text or null")
        if level > ValidationLevel.UNVALIDATED and not raw_evidence:
            raise ValueError(f"candidate group {name} validated level requires evidence")
        return cls(
            level=level,
            values=tuple(values),
            evidence=tuple(raw_evidence),
            note=note,
        )

    @property
    def values_complete(self) -> bool:
        return all(value is not None for _, value in self.values)

    def value_dict(self) -> dict[str, int | float | None]:
        return dict(self.values)


@dataclass(frozen=True)
class CommissioningCandidate:
    candidate_id: str
    environment: str
    source_config_revision: int | None
    groups: tuple[tuple[str, CommissioningCandidateGroup], ...]
    schema_version: int = 1

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CommissioningCandidate":
        if not isinstance(payload, Mapping):
            raise ValueError("commissioning candidate must be a JSON object")
        unknown = set(payload) - {
            "schema_version",
            "candidate_id",
            "environment",
            "source_config_revision",
            "groups",
        }
        if unknown:
            raise ValueError(f"candidate contains unsupported fields: {', '.join(sorted(unknown))}")
        schema_version = payload.get("schema_version", 1)
        if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != 1:
            raise ValueError("unsupported commissioning candidate schema_version")
        candidate_id = payload.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip() or len(candidate_id) > 120:
            raise ValueError("candidate_id must be non-empty text up to 120 characters")
        environment = payload.get("environment")
        if environment != "WORKSHOP":
            raise ValueError("commissioning candidate environment must be WORKSHOP")
        source_revision = payload.get("source_config_revision")
        if source_revision is not None and (
            isinstance(source_revision, bool)
            or not isinstance(source_revision, int)
            or source_revision < 1
        ):
            raise ValueError("source_config_revision must be a positive integer or null")
        raw_groups = payload.get("groups")
        if not isinstance(raw_groups, Mapping):
            raise ValueError("candidate groups must be a JSON object")
        if set(raw_groups) != set(GROUP_FIELDS):
            missing = set(GROUP_FIELDS) - set(raw_groups)
            extra = set(raw_groups) - set(GROUP_FIELDS)
            details = []
            if missing:
                details.append(f"missing={','.join(sorted(missing))}")
            if extra:
                details.append(f"unsupported={','.join(sorted(extra))}")
            raise ValueError(f"candidate group mismatch: {'; '.join(details)}")
        groups = tuple(
            (name, CommissioningCandidateGroup.from_dict(name, raw_groups[name]))
            for name in GROUP_FIELDS
        )
        candidate = cls(
            candidate_id=candidate_id,
            environment=environment,
            source_config_revision=source_revision,
            groups=groups,
            schema_version=schema_version,
        )
        # Reuse the production tuning type for range/pair/monotonic validation.
        ShadowOutputTuning(**candidate.flatten_values())
        return candidate

    def group(self, name: str) -> CommissioningCandidateGroup:
        for group_name, group in self.groups:
            if group_name == name:
                return group
        raise KeyError(name)

    def flatten_values(self) -> dict[str, int | float | None]:
        values: dict[str, int | float | None] = {}
        for _, group in self.groups:
            for field, value in group.values:
                if field in values:
                    raise RuntimeError(f"duplicate tuning field in candidate: {field}")
                values[field] = value
        return values

    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        for name, required in TUNING_GROUP_REQUIREMENTS.items():
            group = self.group(name)
            if not group.values_complete:
                blockers.append(f"CANDIDATE_{name.upper()}_VALUES_INCOMPLETE")
            if group.level < required:
                blockers.append(f"CANDIDATE_{name.upper()}_REQUIRES_{required.name}")
        return tuple(blockers)

    @property
    def complete_for_review(self) -> bool:
        return not self.blockers()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "environment": self.environment,
            "source_config_revision": self.source_config_revision,
            "groups": {
                name: {
                    "level": group.level.name,
                    "values": group.value_dict(),
                    "evidence": list(group.evidence),
                    "note": group.note,
                }
                for name, group in self.groups
            },
        }
