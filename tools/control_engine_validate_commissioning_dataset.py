#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("dataset timestamp must be non-empty text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("dataset timestamp must be timezone-aware")
    return parsed


def numeric_range(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {"min": min(values), "max": max(values)}


def validate_dataset(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2:
        raise ValueError("dataset must contain one session header and at least one sample")
    records = [json.loads(line) for line in lines if line.strip()]
    if not records or records[0].get("record_type") != "session":
        raise ValueError("first dataset record must be session header")
    header = records[0]
    if header.get("schema_version") != 1:
        raise ValueError("unsupported commissioning dataset schema_version")
    if header.get("environment") != "WORKSHOP":
        raise ValueError("commissioning dataset environment must be WORKSHOP")
    if header.get("source") != "ventilation-core:status":
        raise ValueError("commissioning dataset source must be authoritative ventilation-core status")
    if header.get("actuation_authority_granted") is not False:
        raise ValueError("commissioning dataset must be captured before Control Engine authority")
    if header.get("core_writes_performed") is not False:
        raise ValueError("commissioning capture must not perform core writes")

    session_id = header.get("session_id")
    samples = records[1:]
    setpoint_supply: list[float] = []
    setpoint_extract: list[float] = []
    tacho_supply: list[float] = []
    tacho_extract: list[float] = []
    inside_temp: list[float] = []
    outside_temp: list[float] = []
    aq_levels: Counter[str] = Counter()
    calendar_phases: Counter[str] = Counter()
    shadow_statuses: Counter[str] = Counter()
    hardware_ready_count = 0
    output_known_count = 0
    sensor_usable_count = 0
    outside_usable_count = 0
    previous_time: datetime | None = None

    for expected_sequence, record in enumerate(samples):
        if record.get("record_type") != "sample":
            raise ValueError(f"record {expected_sequence + 1} is not a sample")
        if record.get("schema_version") != 1 or record.get("session_id") != session_id:
            raise ValueError("sample schema/session does not match header")
        if record.get("sequence") != expected_sequence:
            raise ValueError("sample sequence must be contiguous from zero")
        captured_at = parse_timestamp(record.get("captured_at_utc"))
        if previous_time is not None and captured_at < previous_time:
            raise ValueError("sample timestamps must be monotonic")
        previous_time = captured_at

        state = record.get("state")
        if not isinstance(state, dict):
            raise ValueError("sample state must be an object")
        shadow = state.get("shadow_automation")
        if not isinstance(shadow, dict):
            raise ValueError("every sample must contain shadow_automation")
        if shadow.get("actuation_supported") is not False:
            raise ValueError("dataset contains an actuating Control Engine sample")
        if state.get("hardware_ready") is True:
            hardware_ready_count += 1
        if state.get("output_state_known") is True:
            output_known_count += 1
        if isinstance(shadow.get("status"), str):
            shadow_statuses[shadow["status"]] += 1

        setpoints = state.get("setpoints") or {}
        for key, target in (
            ("supply_voltage", setpoint_supply),
            ("extract_voltage", setpoint_extract),
        ):
            value = setpoints.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                target.append(float(value))

        tacho = state.get("tacho") or {}
        for channel, target in (("supply", tacho_supply), ("extract", tacho_extract)):
            row = tacho.get(channel) or {}
            value = row.get("rpm")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                target.append(float(value))

        zones = [row for row in shadow.get("zones") or [] if isinstance(row, dict)]
        zone1 = next((row for row in zones if row.get("zone") == "zone-1"), None)
        if zone1 is not None:
            if zone1.get("sensor_usable") is True:
                sensor_usable_count += 1
            if zone1.get("outside_temperature_usable") is True:
                outside_usable_count += 1
            level = zone1.get("air_quality_level")
            if isinstance(level, str):
                aq_levels[level] += 1
            phase = zone1.get("calendar_phase")
            if isinstance(phase, str):
                calendar_phases[phase] += 1
            value = zone1.get("inside_temperature_celsius")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                inside_temp.append(float(value))
            value = zone1.get("outside_temperature_celsius")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                outside_temp.append(float(value))

    count = len(samples)
    warnings: list[str] = []
    if hardware_ready_count != count:
        warnings.append("HARDWARE_NOT_READY_IN_SOME_SAMPLES")
    if output_known_count != count:
        warnings.append("OUTPUT_STATE_UNKNOWN_IN_SOME_SAMPLES")
    if sensor_usable_count == 0:
        warnings.append("NO_USABLE_ZONE1_SEN55_SAMPLES")
    if outside_usable_count == 0:
        warnings.append("NO_USABLE_SUPPLY_TEMPERATURE_SAMPLES")
    if max(setpoint_supply or [0.0]) <= 0.0 and max(setpoint_extract or [0.0]) <= 0.0:
        warnings.append("NO_NONZERO_LOCAL_FAN_SETPOINTS")
    if len(aq_levels) < 2:
        warnings.append("AIR_QUALITY_COVERAGE_TOO_NARROW_FOR_DYNAMICS_TUNING")
    if len(calendar_phases) < 2:
        warnings.append("CALENDAR_PHASE_COVERAGE_TOO_NARROW")

    return {
        "session_id": session_id,
        "environment": "WORKSHOP",
        "samples": count,
        "coverage": {
            "hardware_ready_samples": hardware_ready_count,
            "output_state_known_samples": output_known_count,
            "zone1_sensor_usable_samples": sensor_usable_count,
            "outside_temperature_usable_samples": outside_usable_count,
            "supply_setpoint_v": numeric_range(setpoint_supply),
            "extract_setpoint_v": numeric_range(setpoint_extract),
            "supply_rpm": numeric_range(tacho_supply),
            "extract_rpm": numeric_range(tacho_extract),
            "inside_temperature_c": numeric_range(inside_temp),
            "outside_temperature_c": numeric_range(outside_temp),
            "air_quality_levels": dict(sorted(aq_levels.items())),
            "calendar_phases": dict(sorted(calendar_phases.items())),
            "shadow_statuses": dict(sorted(shadow_statuses.items())),
        },
        "coverage_warnings": warnings,
        "ready_for_manual_commissioning_review": not warnings,
        "tuning_recommendation_generated": False,
        "actuation_authority_granted": False,
        "core_writes_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and summarize a read-only Control Engine workshop commissioning JSONL dataset."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--require-coverage", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate_dataset(args.dataset)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=None if args.compact else 2, sort_keys=True))
    if args.require_coverage and not result["ready_for_manual_commissioning_review"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
