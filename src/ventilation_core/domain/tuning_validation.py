from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Mapping


class ValidationLevel(IntEnum):
    """Evidence strength for one Control Engine tuning group."""

    UNVALIDATED = 0
    SYNTHETIC_VALIDATED = 1
    PHYSICAL_VALIDATED = 2
    WORKSHOP_VALIDATED = 3

    @classmethod
    def from_name(cls, value: Any) -> "ValidationLevel":
        if not isinstance(value, str):
            raise ValueError("validation level must be text")
        try:
            return cls[value]
        except KeyError as exc:
            raise ValueError(f"unsupported validation level: {value!r}") from exc


TUNING_GROUP_REQUIREMENTS: dict[str, ValidationLevel] = {
    "fan_outputs": ValidationLevel.WORKSHOP_VALIDATED,
    "aero_outputs": ValidationLevel.WORKSHOP_VALIDATED,
    "dynamics": ValidationLevel.WORKSHOP_VALIDATED,
    "fan_sensor_fallback": ValidationLevel.WORKSHOP_VALIDATED,
    "aero_sensor_fallback": ValidationLevel.WORKSHOP_VALIDATED,
    "tacho_confirmation": ValidationLevel.PHYSICAL_VALIDATED,
    "tacho_supply_fallback": ValidationLevel.WORKSHOP_VALIDATED,
    "tacho_extract_fallback": ValidationLevel.WORKSHOP_VALIDATED,
    "tacho_both_fallback": ValidationLevel.WORKSHOP_VALIDATED,
}


@dataclass(frozen=True)
class TuningValidationEntry:
    level: ValidationLevel = ValidationLevel.UNVALIDATED
    evidence: tuple[str, ...] = ()
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.level, ValidationLevel):
            raise ValueError("level must be ValidationLevel")
        if self.level > ValidationLevel.UNVALIDATED and not self.evidence:
            raise ValueError("validated tuning requires at least one evidence reference")
        for item in self.evidence:
            if not isinstance(item, str) or not item.strip() or len(item) > 240:
                raise ValueError("evidence references must be non-empty text up to 240 characters")
        if self.note is not None and (
            not isinstance(self.note, str) or not self.note.strip() or len(self.note) > 500
        ):
            raise ValueError("note must be non-empty text up to 500 characters or null")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TuningValidationEntry":
        if not isinstance(payload, Mapping):
            raise ValueError("validation entry must be a JSON object")
        unknown = set(payload) - {"level", "evidence", "note"}
        if unknown:
            raise ValueError(f"validation entry contains unsupported fields: {', '.join(sorted(unknown))}")
        level = ValidationLevel.from_name(payload.get("level", "UNVALIDATED"))
        raw_evidence = payload.get("evidence", [])
        if not isinstance(raw_evidence, list) or any(not isinstance(item, str) for item in raw_evidence):
            raise ValueError("validation evidence must be an array of strings")
        note = payload.get("note")
        return cls(level=level, evidence=tuple(raw_evidence), note=note)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.name,
            "evidence": list(self.evidence),
            "note": self.note,
        }


@dataclass(frozen=True)
class TuningValidationProfile:
    profile: str
    groups: tuple[tuple[str, TuningValidationEntry], ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise ValueError("unsupported tuning validation schema_version")
        if not isinstance(self.profile, str) or not self.profile.strip() or len(self.profile) > 120:
            raise ValueError("validation profile must be non-empty text up to 120 characters")
        names = [name for name, _ in self.groups]
        if set(names) != set(TUNING_GROUP_REQUIREMENTS) or len(names) != len(TUNING_GROUP_REQUIREMENTS):
            raise ValueError("validation profile must define every tuning group exactly once")
        for name, entry in self.groups:
            if name not in TUNING_GROUP_REQUIREMENTS:
                raise ValueError(f"unsupported tuning validation group: {name}")
            if not isinstance(entry, TuningValidationEntry):
                raise ValueError("validation group entry must be TuningValidationEntry")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TuningValidationProfile":
        if not isinstance(payload, Mapping):
            raise ValueError("tuning validation profile must be a JSON object")
        unknown = set(payload) - {"schema_version", "profile", "groups"}
        if unknown:
            raise ValueError(f"validation profile contains unsupported fields: {', '.join(sorted(unknown))}")
        schema_version = payload.get("schema_version", 1)
        if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != 1:
            raise ValueError("unsupported tuning validation schema_version")
        profile = payload.get("profile")
        raw_groups = payload.get("groups")
        if not isinstance(raw_groups, Mapping):
            raise ValueError("validation profile groups must be a JSON object")
        unknown_groups = set(raw_groups) - set(TUNING_GROUP_REQUIREMENTS)
        missing_groups = set(TUNING_GROUP_REQUIREMENTS) - set(raw_groups)
        if unknown_groups:
            raise ValueError(f"unsupported tuning validation groups: {', '.join(sorted(unknown_groups))}")
        if missing_groups:
            raise ValueError(f"missing tuning validation groups: {', '.join(sorted(missing_groups))}")
        groups = tuple(
            (name, TuningValidationEntry.from_dict(raw_groups[name]))
            for name in TUNING_GROUP_REQUIREMENTS
        )
        return cls(profile=profile, groups=groups, schema_version=schema_version)

    def entry(self, name: str) -> TuningValidationEntry:
        for group_name, entry in self.groups:
            if group_name == name:
                return entry
        raise KeyError(name)

    def readiness_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        for name, required in TUNING_GROUP_REQUIREMENTS.items():
            actual = self.entry(name).level
            if actual < required:
                blockers.append(
                    f"VALIDATION_{name.upper()}_REQUIRES_{required.name}"
                )
        return tuple(blockers)

    @property
    def ready_for_actuation_preconditions(self) -> bool:
        return not self.readiness_blockers()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "groups": {name: entry.to_dict() for name, entry in self.groups},
        }
