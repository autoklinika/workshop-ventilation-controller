from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Iterable


@dataclass(frozen=True)
class RollupSample:
    captured_at: str
    metrics: dict[str, Any]


def _path_join(prefix: str, key: str) -> str:
    return key if not prefix else f"{prefix}.{key}"


def _flatten(value: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten(value[key], _path_join(prefix, str(key)), out)
        return

    if isinstance(value, list):
        if prefix.endswith("active_alarms"):
            out[_path_join(prefix, "count")] = len(value)
            return

        address_items: list[tuple[int, dict[str, Any]]] = []
        for item in value:
            if not isinstance(item, dict):
                address_items = []
                break
            address = item.get("slave_address")
            if isinstance(address, bool) or not isinstance(address, int):
                address_items = []
                break
            address_items.append((address, item))

        if address_items and len({address for address, _ in address_items}) == len(address_items):
            for address, item in sorted(address_items, key=lambda pair: pair[0]):
                _flatten(item, f"{prefix}[{address}]", out)
            return

        for index, item in enumerate(value):
            _flatten(item, f"{prefix}[{index}]", out)
        return

    if value is None or not prefix:
        return
    out[prefix] = value


def summarize_metrics(samples: Iterable[RollupSample]) -> dict[str, Any]:
    materialized = list(samples)
    if not materialized:
        raise ValueError("rollup requires at least one sample")

    numeric: dict[str, dict[str, Any]] = {}
    states: dict[str, dict[str, Any]] = {}

    for sample in materialized:
        flat: dict[str, Any] = {}
        _flatten(sample.metrics, "", flat)
        for path, value in flat.items():
            if isinstance(value, bool):
                state = states.setdefault(
                    path,
                    {"count": 0, "last": value, "changes": 0, "true_count": 0},
                )
                if state["count"] and state["last"] != value:
                    state["changes"] += 1
                state["count"] += 1
                state["last"] = value
                if value:
                    state["true_count"] += 1
                continue

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                number = float(value)
                if not math.isfinite(number):
                    continue
                signal = numeric.setdefault(
                    path,
                    {"count": 0, "sum": 0.0, "min": number, "max": number, "last": number},
                )
                signal["count"] += 1
                signal["sum"] += number
                signal["min"] = min(signal["min"], number)
                signal["max"] = max(signal["max"], number)
                signal["last"] = number
                continue

            if isinstance(value, str):
                state = states.setdefault(
                    path,
                    {"count": 0, "last": value, "changes": 0},
                )
                if state["count"] and state["last"] != value:
                    state["changes"] += 1
                state["count"] += 1
                state["last"] = value

    signals = {
        path: {
            "count": signal["count"],
            "min": signal["min"],
            "max": signal["max"],
            "avg": signal["sum"] / signal["count"],
            "last": signal["last"],
        }
        for path, signal in sorted(numeric.items())
        if signal["count"]
    }

    normalized_states: dict[str, dict[str, Any]] = {}
    for path, state in sorted(states.items()):
        normalized = {
            "count": state["count"],
            "last": state["last"],
            "changes": state["changes"],
        }
        if "true_count" in state:
            normalized["true_count"] = state["true_count"]
        normalized_states[path] = normalized

    return {
        "sample_count": len(materialized),
        "first_captured_at": materialized[0].captured_at,
        "last_captured_at": materialized[-1].captured_at,
        "signals": signals,
        "states": normalized_states,
    }


def floor_utc(value: datetime, bucket_seconds: int) -> datetime:
    if bucket_seconds < 1:
        raise ValueError("bucket_seconds must be positive")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    utc = value.astimezone(timezone.utc)
    epoch = int(utc.timestamp())
    floored = epoch - (epoch % bucket_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)
