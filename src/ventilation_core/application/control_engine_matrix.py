from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping, Sequence

from ventilation_core.application.control_engine_scenario import ControlEngineScenarioRunner


_MATRIX_KEYS = {
    "schema_version",
    "name",
    "start_utc",
    "control_engine",
    "base_step",
    "dimensions",
}
_DIMENSION_KEYS = {"name", "variants"}
_VARIANT_KEYS = {"id", "step"}
_MATRIX_STEP_KEYS = {
    "calendar",
    "sensor_1",
    "sensor_2",
    "zigbee_supply",
    "zigbee_extract",
    "hardware_ready",
    "output_state_known",
    "critical_alarm",
}


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a JSON object")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a JSON array")
    return value


def _strict_keys(payload: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{field} contains unsupported fields: {', '.join(sorted(unknown))}")


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 64:
        raise ValueError(f"{field} must be non-empty trimmed text up to 64 characters")
    return value


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = deepcopy(dict(base))
    for key, value in override.items():
        previous = result.get(key)
        if isinstance(previous, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(previous, value)
        else:
            result[key] = deepcopy(value)
    return result


@dataclass(frozen=True)
class MatrixVariant:
    variant_id: str
    step: Mapping[str, Any]


@dataclass(frozen=True)
class MatrixDimension:
    name: str
    variants: tuple[MatrixVariant, ...]


@dataclass(frozen=True)
class MatrixRunResult:
    name: str
    policy_version: str
    dimensions: tuple[str, ...]
    cases: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "name": self.name,
            "policy_version": self.policy_version,
            "actuation_supported": False,
            "dimensions": list(self.dimensions),
            "case_count": len(self.cases),
            "cases": list(self.cases),
        }


class ControlEngineMatrixRunner:
    """Cartesian replay of independent synthetic Control Engine SHADOW cases.

    Every matrix case is evaluated through a fresh ControlEngineScenarioRunner so
    dynamics/hysteresis state never leaks between combinations. The matrix runner
    has no hardware, process, socket, GPIO, DAC, AERO-executor, host-power or
    systemd boundary.
    """

    def __init__(self, *, max_cases: int = 1024) -> None:
        if isinstance(max_cases, bool) or not isinstance(max_cases, int) or max_cases <= 0:
            raise ValueError("max_cases must be a positive integer")
        self._max_cases = max_cases

    def run(self, payload: Mapping[str, Any]) -> MatrixRunResult:
        payload = _mapping(payload, "matrix")
        _strict_keys(payload, _MATRIX_KEYS, "matrix")

        schema_version = payload.get("schema_version", 1)
        if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version != 1:
            raise ValueError("unsupported matrix schema_version")

        name = payload.get("name")
        if not isinstance(name, str) or not name.strip() or name != name.strip() or len(name) > 120:
            raise ValueError("matrix.name must be non-empty trimmed text up to 120 characters")

        start_utc = payload.get("start_utc")
        if not isinstance(start_utc, str) or not start_utc.strip():
            raise ValueError("matrix.start_utc must be non-empty ISO-8601 text")

        control_engine = _mapping(payload.get("control_engine"), "matrix.control_engine")
        base_step = _mapping(payload.get("base_step"), "matrix.base_step")
        _strict_keys(base_step, _MATRIX_STEP_KEYS, "matrix.base_step")
        dimensions = self._dimensions(payload.get("dimensions"))

        case_count = 1
        for dimension in dimensions:
            case_count *= len(dimension.variants)
        if case_count > self._max_cases:
            raise ValueError(
                f"matrix expands to {case_count} cases; configured maximum is {self._max_cases}"
            )

        cases: list[dict[str, Any]] = []
        policy_version: str | None = None
        for case_index, selected in enumerate(
            product(*(dimension.variants for dimension in dimensions))
        ):
            step: dict[str, Any] = deepcopy(dict(base_step))
            selection: dict[str, str] = {}
            case_parts: list[str] = []
            for dimension, variant in zip(dimensions, selected, strict=True):
                step = _deep_merge(step, variant.step)
                selection[dimension.name] = variant.variant_id
                case_parts.append(f"{dimension.name}={variant.variant_id}")
            step["at_seconds"] = 0.0

            scenario = {
                "schema_version": 1,
                "name": f"matrix-case-{case_index}",
                "start_utc": start_utc,
                "control_engine": deepcopy(dict(control_engine)),
                "steps": [step],
            }
            scenario_result = ControlEngineScenarioRunner().run(scenario).to_dict()
            if policy_version is None:
                policy_version = str(scenario_result["policy_version"])
            elif scenario_result["policy_version"] != policy_version:
                raise RuntimeError("matrix cases unexpectedly used different policy versions")

            shadow = scenario_result["steps"][0]["shadow"]
            self._assert_non_actuating(shadow)
            cases.append(
                {
                    "case_id": "|".join(case_parts),
                    "selection": selection,
                    "shadow": shadow,
                }
            )

        assert policy_version is not None
        return MatrixRunResult(
            name=name,
            policy_version=policy_version,
            dimensions=tuple(dimension.name for dimension in dimensions),
            cases=tuple(cases),
        )

    def _dimensions(self, raw: Any) -> tuple[MatrixDimension, ...]:
        values = _sequence(raw, "matrix.dimensions")
        if not values:
            raise ValueError("matrix.dimensions must contain at least one dimension")

        dimensions: list[MatrixDimension] = []
        names: set[str] = set()
        for index, raw_dimension in enumerate(values):
            field = f"matrix.dimensions[{index}]"
            dimension_payload = _mapping(raw_dimension, field)
            _strict_keys(dimension_payload, _DIMENSION_KEYS, field)
            name = _identifier(dimension_payload.get("name"), f"{field}.name")
            if name in names:
                raise ValueError(f"duplicate matrix dimension name: {name}")
            names.add(name)

            raw_variants = _sequence(dimension_payload.get("variants"), f"{field}.variants")
            if not raw_variants:
                raise ValueError(f"{field}.variants must contain at least one variant")
            variants: list[MatrixVariant] = []
            variant_ids: set[str] = set()
            for variant_index, raw_variant in enumerate(raw_variants):
                variant_field = f"{field}.variants[{variant_index}]"
                variant_payload = _mapping(raw_variant, variant_field)
                _strict_keys(variant_payload, _VARIANT_KEYS, variant_field)
                variant_id = _identifier(
                    variant_payload.get("id"),
                    f"{variant_field}.id",
                )
                if variant_id in variant_ids:
                    raise ValueError(f"duplicate variant id {variant_id!r} in dimension {name!r}")
                variant_ids.add(variant_id)
                step = _mapping(variant_payload.get("step", {}), f"{variant_field}.step")
                _strict_keys(step, _MATRIX_STEP_KEYS, f"{variant_field}.step")
                variants.append(MatrixVariant(variant_id=variant_id, step=deepcopy(dict(step))))
            dimensions.append(MatrixDimension(name=name, variants=tuple(variants)))

        return tuple(dimensions)

    @staticmethod
    def _assert_non_actuating(shadow: Mapping[str, Any]) -> None:
        if shadow.get("actuation_supported") is not False:
            raise RuntimeError("matrix evaluator unexpectedly supports actuation")
        for zone in shadow.get("zones") or []:
            if zone.get("proposed_supply_voltage") is not None:
                raise RuntimeError("matrix exposed physical supply voltage proposal")
            if zone.get("proposed_extract_voltage") is not None:
                raise RuntimeError("matrix exposed physical extract voltage proposal")
