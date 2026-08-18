from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


SCHEMA_VERSION = 1
DEFAULT_RUNTIME_POLICY_PATH = Path("/etc/workshop-ventilation/alerts-v2.toml")

_ALLOWED_REACTIONS = frozenset(
    {
        "continue",
        "continue_degraded",
        "fallback_local",
        "recover_safe_outputs",
        "safe_state",
        "block_gui",
    }
)
_ALLOWED_COLORS = frozenset({"green", "blue", "yellow", "orange", "red"})
_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

_REQUIRED_BEHAVIOR = {
    "highest_active_weight_controls_hmi": True,
    "acknowledgement_changes_weight": False,
    "acknowledgement_changes_hmi_color": False,
    "cleared_alerts_affect_hmi": False,
    "unknown_alert_policy": "reject",
    "invalid_configuration_policy": "reject_keep_last_known_good",
}

_WEIGHT_PROFILE = {
    "normal": (0, "normal", "green"),
    "info": (1, "info", "blue"),
    "warning": (2, "warning", "yellow"),
    "alarm": (3, "alarm", "orange"),
    "critical": (4, "critical", "red"),
}

_ALERT_REQUIRED_FIELDS = frozenset(
    {
        "enabled",
        "owner",
        "category",
        "weight",
        "severity",
        "reaction",
        "scope",
        "affects_control",
        "hmi_color",
        "correlation_group",
        "correlation_priority",
        "title",
        "message",
    }
)
_ALERT_OPTIONAL_FIELDS = frozenset({"parameters"})

_TACHO_DIAGNOSTIC_CODES = frozenset(
    {
        "TACHO_MONITOR_UNAVAILABLE",
        "TACHO_CONFIGURATION_INVALID",
    }
)
_FAN_FEEDBACK_CODES = frozenset(
    {
        "FAN_NO_ROTATION_FEEDBACK",
        "FAN_RPM_OUT_OF_RANGE",
    }
)
_REQUIRED_SAFETY_ALERTS = frozenset(
    {
        "DAC_STATE_UNCERTAIN",
        "DAC_COMMUNICATION_LOST",
        "TACHO_MONITOR_UNAVAILABLE",
        "TACHO_CONFIGURATION_INVALID",
    }
)
_NON_CONTROL_DOMAINS = frozenset(
    {
        "HMI_CM5_COMMUNICATION_LOST",
        "WEATHER_UNAVAILABLE",
        "WEATHER_DATA_STALE",
        "AI_BRIDGE_SYNC_TEMPORARY_FAILURE",
        "AI_BRIDGE_BACKLOG_HIGH",
        "AI_ADVISORY_UNAVAILABLE",
        "NAS_STORAGE_UNAVAILABLE",
        "SERVICE_AGENT_UNAVAILABLE",
        "SERVICE_NETWORK_AP_UNAVAILABLE",
        "SERVICE_NETWORK_DHCP_UNAVAILABLE",
        "SERVICE_NETWORK_FIREWALL_INVALID",
    }
)


class AlertPolicyError(ValueError):
    """Raised when an AlertV2 policy cannot be parsed or violates the contract."""

    def __init__(self, errors: str | list[str] | tuple[str, ...]) -> None:
        if isinstance(errors, str):
            normalized = (errors,)
        else:
            normalized = tuple(str(error) for error in errors)
        self.errors = normalized
        super().__init__("; ".join(normalized))


@dataclass(frozen=True)
class AlertPolicyEntry:
    code: str
    enabled: bool
    owner: str
    category: str
    weight: int
    severity: str
    reaction: str
    scope: str
    affects_control: bool
    hmi_color: str
    correlation_group: str
    correlation_priority: int
    title: str
    message: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class AlertPolicy:
    schema_version: int
    policy_version: str
    policy_name: str
    description: str
    runtime_path: str
    behavior: Mapping[str, Any]
    alerts: Mapping[str, AlertPolicyEntry]
    sha256: str
    source_path: Path

    @property
    def alert_count(self) -> int:
        return len(self.alerts)

    def get(self, code: str) -> AlertPolicyEntry | None:
        return self.alerts.get(code)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_token(value: object, *, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        errors.append(f"{field} must match {_TOKEN_RE.pattern!r}")


def _validate_parameters(value: object, *, field: str, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"{field} must be a TOML table")
        return

    def walk(item: object, path: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or not key:
                    errors.append(f"{path} contains an invalid key")
                    continue
                walk(child, f"{path}.{key}")
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")
            return
        if isinstance(item, (str, int, float, bool)) or item is None:
            return
        # datetime/date/time objects produced by tomllib are harmless configuration
        # values, but detector code must explicitly opt in before using them.
        module = type(item).__module__
        if module == "datetime":
            return
        errors.append(f"{path} contains unsupported value type {type(item).__name__}")

    walk(value, field)


def validate_alert_policy_document(document: object) -> tuple[str, ...]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ("policy root must be a TOML table",)

    allowed_top = {
        "schema_version",
        "policy_version",
        "policy_name",
        "description",
        "runtime_path",
        "behavior",
        "weight",
        "alerts",
    }
    unknown_top = sorted(set(document) - allowed_top)
    if unknown_top:
        errors.append(f"unknown top-level fields: {', '.join(unknown_top)}")

    schema_version = document.get("schema_version")
    if not _is_int(schema_version) or schema_version != SCHEMA_VERSION:
        errors.append(f"schema_version must be exactly {SCHEMA_VERSION}")

    for field in ("policy_version", "policy_name", "description", "runtime_path"):
        if not _nonempty_string(document.get(field)):
            errors.append(f"{field} must be a non-empty string")
    runtime_path = document.get("runtime_path")
    if isinstance(runtime_path, str) and not runtime_path.startswith("/"):
        errors.append("runtime_path must be an absolute path")

    behavior = document.get("behavior")
    if not isinstance(behavior, dict):
        errors.append("behavior must be a TOML table")
    else:
        missing = sorted(set(_REQUIRED_BEHAVIOR) - set(behavior))
        unknown = sorted(set(behavior) - set(_REQUIRED_BEHAVIOR))
        if missing:
            errors.append(f"behavior missing fields: {', '.join(missing)}")
        if unknown:
            errors.append(f"behavior has unknown fields: {', '.join(unknown)}")
        for field, expected in _REQUIRED_BEHAVIOR.items():
            if field in behavior and behavior[field] != expected:
                errors.append(
                    f"behavior.{field} must be {expected!r}; safety semantics are not configurable"
                )

    weights = document.get("weight")
    weight_by_value: dict[int, tuple[str, str]] = {}
    if not isinstance(weights, dict):
        errors.append("weight must be a TOML table")
    else:
        missing = sorted(set(_WEIGHT_PROFILE) - set(weights))
        unknown = sorted(set(weights) - set(_WEIGHT_PROFILE))
        if missing:
            errors.append(f"weight missing profiles: {', '.join(missing)}")
        if unknown:
            errors.append(f"weight has unknown profiles: {', '.join(unknown)}")
        for name, expected in _WEIGHT_PROFILE.items():
            raw = weights.get(name)
            if not isinstance(raw, dict):
                errors.append(f"weight.{name} must be a TOML table")
                continue
            if set(raw) != {"value", "severity", "hmi_color"}:
                errors.append(
                    f"weight.{name} must contain exactly value, severity and hmi_color"
                )
                continue
            actual = (raw.get("value"), raw.get("severity"), raw.get("hmi_color"))
            if actual != expected:
                errors.append(
                    f"weight.{name} must be value={expected[0]}, severity={expected[1]!r}, "
                    f"hmi_color={expected[2]!r}"
                )
            if _is_int(raw.get("value")) and isinstance(raw.get("severity"), str) and isinstance(
                raw.get("hmi_color"), str
            ):
                weight_by_value[int(raw["value"])] = (
                    str(raw["severity"]),
                    str(raw["hmi_color"]),
                )

    alerts = document.get("alerts")
    if not isinstance(alerts, dict) or not alerts:
        errors.append("alerts must be a non-empty TOML table")
        return tuple(errors)

    for code, raw in alerts.items():
        prefix = f"alerts.{code}"
        if not isinstance(code, str) or _CODE_RE.fullmatch(code) is None:
            errors.append(f"invalid alert code {code!r}; expected {_CODE_RE.pattern!r}")
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be a TOML table")
            continue

        fields = set(raw)
        missing = sorted(_ALERT_REQUIRED_FIELDS - fields)
        unknown = sorted(fields - _ALERT_REQUIRED_FIELDS - _ALERT_OPTIONAL_FIELDS)
        if missing:
            errors.append(f"{prefix} missing fields: {', '.join(missing)}")
        if unknown:
            errors.append(
                f"{prefix} has unknown fields: {', '.join(unknown)}; detector parameters belong under .parameters"
            )

        if not isinstance(raw.get("enabled"), bool):
            errors.append(f"{prefix}.enabled must be boolean")
        if not isinstance(raw.get("affects_control"), bool):
            errors.append(f"{prefix}.affects_control must be boolean")

        for field in ("owner", "category", "scope", "correlation_group"):
            _validate_token(raw.get(field), field=f"{prefix}.{field}", errors=errors)

        weight = raw.get("weight")
        if not _is_int(weight) or not 0 <= int(weight) <= 4:
            errors.append(f"{prefix}.weight must be an integer in range 0..4")
        else:
            expected_semantics = weight_by_value.get(int(weight)) or {
                value: (severity, color)
                for _, (value, severity, color) in _WEIGHT_PROFILE.items()
            }.get(int(weight))
            if expected_semantics is not None:
                expected_severity, expected_color = expected_semantics
                if raw.get("severity") != expected_severity:
                    errors.append(
                        f"{prefix}.severity must be {expected_severity!r} for weight {weight}"
                    )
                if raw.get("hmi_color") != expected_color:
                    errors.append(
                        f"{prefix}.hmi_color must be {expected_color!r} for weight {weight}"
                    )

        reaction = raw.get("reaction")
        if reaction not in _ALLOWED_REACTIONS:
            errors.append(
                f"{prefix}.reaction must be one of {', '.join(sorted(_ALLOWED_REACTIONS))}"
            )
        color = raw.get("hmi_color")
        if color not in _ALLOWED_COLORS:
            errors.append(f"{prefix}.hmi_color must be one of {', '.join(sorted(_ALLOWED_COLORS))}")

        priority = raw.get("correlation_priority")
        if not _is_int(priority) or not 0 <= int(priority) <= 100:
            errors.append(f"{prefix}.correlation_priority must be an integer in range 0..100")

        for field in ("severity", "title", "message"):
            if not _nonempty_string(raw.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string")

        _validate_parameters(raw.get("parameters"), field=f"{prefix}.parameters", errors=errors)

    for code in sorted(_REQUIRED_SAFETY_ALERTS):
        raw = alerts.get(code)
        if not isinstance(raw, dict):
            errors.append(f"required safety policy {code} is missing")
        elif raw.get("enabled") is not True:
            errors.append(f"required safety policy {code} cannot be disabled")

    for code in sorted(_TACHO_DIAGNOSTIC_CODES):
        raw = alerts.get(code)
        if not isinstance(raw, dict):
            continue
        if raw.get("reaction") not in {"continue", "continue_degraded"}:
            errors.append(
                f"{code} cannot request a control/safe-state reaction; loss of TACHO never stops ventilation"
            )
        if raw.get("affects_control") is not False:
            errors.append(
                f"{code}.affects_control must be false; loss of TACHO is diagnostic only"
            )

    for code in sorted(_FAN_FEEDBACK_CODES):
        raw = alerts.get(code)
        if not isinstance(raw, dict):
            continue
        if raw.get("reaction") in {"safe_state", "recover_safe_outputs"}:
            errors.append(
                f"{code} cannot request a global DAC safe-state reaction under the current AlertV2 contract"
            )

    dac_lost = alerts.get("DAC_COMMUNICATION_LOST")
    if isinstance(dac_lost, dict):
        if dac_lost.get("reaction") != "safe_state":
            errors.append("DAC_COMMUNICATION_LOST.reaction must remain 'safe_state'")
        if dac_lost.get("affects_control") is not True:
            errors.append("DAC_COMMUNICATION_LOST.affects_control must remain true")
        if dac_lost.get("weight") != 4:
            errors.append("DAC_COMMUNICATION_LOST.weight must remain 4")

    dac_uncertain = alerts.get("DAC_STATE_UNCERTAIN")
    if isinstance(dac_uncertain, dict):
        if dac_uncertain.get("reaction") != "recover_safe_outputs":
            errors.append("DAC_STATE_UNCERTAIN.reaction must remain 'recover_safe_outputs'")
        if dac_uncertain.get("affects_control") is not True:
            errors.append("DAC_STATE_UNCERTAIN.affects_control must remain true")

    dac_mismatch = alerts.get("DAC_OUTPUT_MISMATCH")
    if isinstance(dac_mismatch, dict):
        if dac_mismatch.get("reaction") != "safe_state":
            errors.append("DAC_OUTPUT_MISMATCH.reaction must remain 'safe_state'")
        if dac_mismatch.get("affects_control") is not True:
            errors.append("DAC_OUTPUT_MISMATCH.affects_control must remain true")

    hmi = alerts.get("HMI_CM5_COMMUNICATION_LOST")
    if isinstance(hmi, dict):
        if hmi.get("reaction") != "block_gui":
            errors.append("HMI_CM5_COMMUNICATION_LOST.reaction must remain 'block_gui'")
        if hmi.get("affects_control") is not False:
            errors.append("HMI_CM5_COMMUNICATION_LOST must not affect autonomous core control")

    for code in sorted(_NON_CONTROL_DOMAINS):
        raw = alerts.get(code)
        if not isinstance(raw, dict):
            continue
        if raw.get("affects_control") is not False:
            errors.append(f"{code}.affects_control must remain false")
        if raw.get("reaction") not in {"continue", "continue_degraded", "block_gui"}:
            errors.append(f"{code}.reaction cannot directly control ventilation")

    return tuple(errors)


def load_alert_policy(path: str | Path) -> AlertPolicy:
    source_path = Path(path)
    try:
        raw_bytes = source_path.read_bytes()
    except OSError as exc:
        raise AlertPolicyError(f"cannot read policy {source_path}: {exc}") from exc

    try:
        document = tomllib.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise AlertPolicyError(f"cannot parse TOML policy {source_path}: {exc}") from exc

    errors = validate_alert_policy_document(document)
    if errors:
        raise AlertPolicyError(errors)

    raw_alerts = document["alerts"]
    alerts: dict[str, AlertPolicyEntry] = {}
    for code, raw in raw_alerts.items():
        parameters = raw.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        alerts[code] = AlertPolicyEntry(
            code=code,
            enabled=raw["enabled"],
            owner=raw["owner"],
            category=raw["category"],
            weight=raw["weight"],
            severity=raw["severity"],
            reaction=raw["reaction"],
            scope=raw["scope"],
            affects_control=raw["affects_control"],
            hmi_color=raw["hmi_color"],
            correlation_group=raw["correlation_group"],
            correlation_priority=raw["correlation_priority"],
            title=raw["title"],
            message=raw["message"],
            parameters=MappingProxyType(dict(parameters)),
        )

    return AlertPolicy(
        schema_version=document["schema_version"],
        policy_version=document["policy_version"],
        policy_name=document["policy_name"],
        description=document["description"],
        runtime_path=document["runtime_path"],
        behavior=MappingProxyType(dict(document["behavior"])),
        alerts=MappingProxyType(alerts),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        source_path=source_path,
    )
