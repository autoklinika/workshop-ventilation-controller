from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Callable, Protocol

from .config import WebUiConfig


class HistoryProvider(Protocol):
    def query(
        self,
        *,
        start_at: str | None = None,
        end_at: str | None = None,
        limit: int = 720,
        resolution: str = "raw",
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class HistorySeriesSpec:
    id: str
    label: str
    unit: str
    group: str
    zone: str
    digits: int
    path: str | None = None
    zigbee_role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "unit": self.unit,
            "group": self.group,
            "zone": self.zone,
            "digits": self.digits,
        }


class HistorySeriesService:
    """Prepare stable time-series payloads for the browser.

    SQLite/raw telemetry layout stays behind this boundary. The GUI requests stable
    series IDs and receives already selected resolution, metadata, gaps and points.
    The service does not classify air quality or calculate trends; it only projects
    recorded numeric telemetry and existing rollups.
    """

    MAX_SERIES_PER_QUERY = 16
    MAX_SOURCE_SAMPLES = 2500
    RESOLUTION_SECONDS = {
        "raw": 5,
        "1m": 60,
        "15m": 15 * 60,
        "1h": 60 * 60,
        "1d": 24 * 60 * 60,
    }
    RANGE_PRESETS = {
        "1h": ("1 godzina", timedelta(hours=1)),
        "24h": ("24 godziny", timedelta(hours=24)),
        "7d": ("7 dni", timedelta(days=7)),
        "30d": ("30 dni", timedelta(days=30)),
        "90d": ("90 dni", timedelta(days=90)),
        "1y": ("1 rok", timedelta(days=365)),
    }

    def __init__(
        self,
        provider: HistoryProvider,
        config: WebUiConfig,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._config = config
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._specs = self._build_specs(config)

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "resolutions": ["auto", "raw", "1m", "15m", "1h", "1d"],
            "ranges": [
                {"id": range_id, "label": label}
                for range_id, (label, _duration) in self.RANGE_PRESETS.items()
            ],
            "series": [spec.to_dict() for spec in self._specs.values()],
            "long_range_rollups_ready": True,
        }

    def query(self, body: dict[str, Any]) -> dict[str, Any]:
        requested = body.get("series")
        if not isinstance(requested, list) or not requested:
            raise ValueError("history series must be a non-empty JSON list")
        if len(requested) > self.MAX_SERIES_PER_QUERY:
            raise ValueError(
                f"history series may contain at most {self.MAX_SERIES_PER_QUERY} entries"
            )
        if any(not isinstance(item, str) or not item for item in requested):
            raise ValueError("history series identifiers must be non-empty strings")
        if len(set(requested)) != len(requested):
            raise ValueError("history series identifiers must be unique")

        unknown = [series_id for series_id in requested if series_id not in self._specs]
        if unknown:
            raise ValueError(f"unknown history series: {unknown}")

        start, end, range_id = self._resolve_range(body)
        resolution_request = body.get("resolution", "auto")
        supported = {"auto", *self.RESOLUTION_SECONDS.keys()}
        if resolution_request not in supported:
            raise ValueError(
                "history series resolution must be one of: auto, raw, 1m, 15m, 1h, 1d"
            )
        resolution = (
            self._auto_resolution(end - start)
            if resolution_request == "auto"
            else resolution_request
        )
        limit = self._source_limit(start, end, resolution)

        samples = self._provider.query(
            start_at=self._format_time(start),
            end_at=self._format_time(end),
            limit=limit,
            resolution=resolution,
        )

        series_payload = [
            self._project_series(self._specs[series_id], samples, resolution)
            for series_id in requested
        ]
        return {
            "schema_version": 1,
            "range": {
                "preset": range_id,
                "start": self._format_time(start),
                "end": self._format_time(end),
            },
            "resolution": resolution,
            "expected_step_seconds": self.RESOLUTION_SECONDS[resolution],
            "series": series_payload,
        }

    def _resolve_range(self, body: dict[str, Any]) -> tuple[datetime, datetime, str | None]:
        range_id = body.get("range")
        if range_id is not None:
            if range_id not in self.RANGE_PRESETS:
                raise ValueError(f"unsupported history range: {range_id}")
            if body.get("start_at") is not None:
                raise ValueError("start_at cannot be combined with a history range preset")
            end = (
                self._parse_time(body.get("end_at"), "end_at")
                if body.get("end_at")
                else self._now_utc()
            )
            duration = self.RANGE_PRESETS[range_id][1]
            return end - duration, end, range_id

        start = self._parse_time(body.get("start_at"), "start_at")
        end = self._parse_time(body.get("end_at"), "end_at")
        if start >= end:
            raise ValueError("history start_at must be earlier than end_at")
        return start, end, None

    def _now_utc(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("history clock must return timezone-aware datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_time(value: Any, name: str) -> datetime:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty ISO-8601 string")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} must be a valid ISO-8601 datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{name} must include a timezone")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _auto_resolution(span: timedelta) -> str:
        seconds = span.total_seconds()
        if seconds <= 2 * 60 * 60:
            return "raw"
        if seconds <= 2 * 24 * 60 * 60:
            return "1m"
        if seconds <= 14 * 24 * 60 * 60:
            return "15m"
        if seconds <= 120 * 24 * 60 * 60:
            return "1h"
        return "1d"

    def _source_limit(self, start: datetime, end: datetime, resolution: str) -> int:
        seconds = (end - start).total_seconds()
        if seconds <= 0:
            raise ValueError("history range must be positive")
        bucket_seconds = self.RESOLUTION_SECONDS[resolution]
        # +2 protects range edges/bucket overlap without silently truncating the start.
        expected = math.ceil(seconds / bucket_seconds) + 2
        if expected > self.MAX_SOURCE_SAMPLES:
            raise ValueError(
                "history range is too large for current stored resolution; "
                "use a shorter range or a coarser resolution"
            )
        return max(1, expected)

    def _project_series(
        self,
        spec: HistorySeriesSpec,
        samples: list[dict[str, Any]],
        resolution: str,
    ) -> dict[str, Any]:
        points: list[dict[str, Any]] = []
        missing = 0
        for sample in samples:
            if resolution == "raw":
                point = self._raw_point(spec, sample)
            else:
                point = self._rollup_point(spec, sample)
            if point is None:
                continue
            if self._point_missing(point, resolution):
                missing += 1
            points.append(point)

        gap_count = self._mark_gaps(points, self.RESOLUTION_SECONDS[resolution])
        return {
            **spec.to_dict(),
            "points": points,
            "point_count": len(points),
            "missing_points": missing,
            "gap_count": gap_count,
        }

    @staticmethod
    def _point_missing(point: dict[str, Any], resolution: str) -> bool:
        if resolution == "raw":
            return point.get("value") is None
        return point.get("avg") is None

    @classmethod
    def _mark_gaps(cls, points: list[dict[str, Any]], step_seconds: int) -> int:
        previous: datetime | None = None
        gaps = 0
        # Use 2.5x expected interval so ordinary scheduling jitter is not a gap.
        threshold = step_seconds * 2.5
        for point in points:
            point["gap_before"] = False
            raw_time = point.get("t")
            if not isinstance(raw_time, str):
                continue
            try:
                current = cls._parse_time(raw_time, "point time")
            except ValueError:
                continue
            if previous is not None and (current - previous).total_seconds() > threshold:
                point["gap_before"] = True
                gaps += 1
            previous = current
        return gaps

    def _raw_point(self, spec: HistorySeriesSpec, sample: dict[str, Any]) -> dict[str, Any] | None:
        captured_at = sample.get("captured_at")
        metrics = sample.get("metrics")
        if not isinstance(captured_at, str) or not isinstance(metrics, dict):
            return None
        value = (
            self._zigbee_raw_value(metrics, spec.zigbee_role)
            if spec.zigbee_role
            else self._numeric_path(metrics, spec.path)
        )
        return {"t": captured_at, "value": value}

    def _rollup_point(self, spec: HistorySeriesSpec, sample: dict[str, Any]) -> dict[str, Any] | None:
        bucket_start = sample.get("bucket_start")
        rollup = sample.get("rollup")
        if not isinstance(bucket_start, str) or not isinstance(rollup, dict):
            return None
        sample_count = sample.get("sample_count")
        signal = (
            self._zigbee_rollup_signal(rollup, spec.zigbee_role)
            if spec.zigbee_role
            else self._rollup_signal(rollup, spec.path)
        )
        if signal is None:
            return {
                "t": bucket_start,
                "avg": None,
                "min": None,
                "max": None,
                "last": None,
                "count": 0,
                "sample_count": int(sample_count) if isinstance(sample_count, int) else 0,
                "coverage": 0.0,
            }
        signal_count = int(signal.get("count", 0)) if isinstance(signal.get("count"), int) else 0
        source_count = int(sample_count) if isinstance(sample_count, int) else 0
        coverage = signal_count / source_count if source_count > 0 else 0.0
        return {
            "t": bucket_start,
            "avg": self._finite_number(signal.get("avg")),
            "min": self._finite_number(signal.get("min")),
            "max": self._finite_number(signal.get("max")),
            "last": self._finite_number(signal.get("last")),
            "count": signal_count,
            "sample_count": source_count,
            "coverage": coverage,
        }

    @classmethod
    def _numeric_path(cls, value: dict[str, Any], path: str | None) -> float | None:
        if not path:
            return None
        current: Any = value
        for segment in path.split("."):
            if "[" in segment and segment.endswith("]"):
                key, selector = segment[:-1].split("[", 1)
                if not isinstance(current, dict):
                    return None
                rows = current.get(key)
                if not isinstance(rows, list):
                    return None
                try:
                    address = int(selector)
                except ValueError:
                    return None
                current = next(
                    (
                        row
                        for row in rows
                        if isinstance(row, dict) and row.get("slave_address") == address
                    ),
                    None,
                )
                if current is None:
                    return None
                continue

            if not isinstance(current, dict) or segment not in current:
                return None
            current = current[segment]
        return cls._finite_number(current)

    @classmethod
    def _finite_number(cls, value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    @staticmethod
    def _rollup_signal(rollup: dict[str, Any], path: str | None) -> dict[str, Any] | None:
        if not path:
            return None
        signals = rollup.get("signals")
        if not isinstance(signals, dict):
            return None
        signal = signals.get(path)
        return signal if isinstance(signal, dict) else None

    @classmethod
    def _zigbee_raw_value(cls, metrics: dict[str, Any], role: str | None) -> float | None:
        if not role:
            return None
        zigbee = metrics.get("zigbee")
        if not isinstance(zigbee, dict):
            return None
        for list_name in ("devices", "sensor_list"):
            rows = zigbee.get(list_name)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or row.get("role") != role:
                    continue
                return cls._finite_number(row.get("temperature_celsius"))
        return None

    @classmethod
    def _zigbee_rollup_signal(
        cls,
        rollup: dict[str, Any],
        role: str | None,
    ) -> dict[str, Any] | None:
        if not role:
            return None
        signals = rollup.get("signals")
        states = rollup.get("states")
        if not isinstance(signals, dict) or not isinstance(states, dict):
            return None

        for list_name in ("devices", "sensor_list"):
            prefix = f"zigbee.{list_name}["
            suffix = "].role"
            for state_path, state in states.items():
                if not (
                    isinstance(state_path, str)
                    and state_path.startswith(prefix)
                    and state_path.endswith(suffix)
                    and isinstance(state, dict)
                    and state.get("last") == role
                ):
                    continue
                index = state_path[len(prefix) : -len(suffix)]
                signal = signals.get(
                    f"zigbee.{list_name}[{index}].temperature_celsius"
                )
                if isinstance(signal, dict):
                    return signal
        return None

    @staticmethod
    def _build_specs(config: WebUiConfig) -> dict[str, HistorySeriesSpec]:
        specs: list[HistorySeriesSpec] = []

        def add_air(zone_id: str, zone_label: str, address: int) -> None:
            base = f"sensor_bus.nodes[{address}].reading"
            fields = (
                ("pm1_0", "PM1.0", "µg/m³", "pm1_0_ug_m3", 1),
                ("pm2_5", "PM2.5", "µg/m³", "pm2_5_ug_m3", 1),
                ("pm4_0", "PM4", "µg/m³", "pm4_0_ug_m3", 1),
                ("pm10_0", "PM10", "µg/m³", "pm10_0_ug_m3", 1),
                ("voc_index", "VOC Index", "", "voc_index", 0),
                ("nox_index", "NOx Index", "", "nox_index", 0),
                ("temperature", "Temperatura", "°C", "temperature_celsius", 1),
                ("humidity", "Wilgotność", "%", "humidity_percent", 1),
            )
            for suffix, label, unit, field, digits in fields:
                specs.append(
                    HistorySeriesSpec(
                        id=f"{zone_id}.air.{suffix}",
                        label=f"{zone_label} · {label}",
                        unit=unit,
                        group=f"{zone_id}.air",
                        zone=zone_id,
                        digits=digits,
                        path=f"{base}.{field}",
                    )
                )

        add_air("zone1", config.zone1_name, config.zone1_sensor_address)
        add_air("zone2", config.zone2_name, config.zone2_sensor_address)

        specs.extend(
            [
                HistorySeriesSpec(
                    "zone1.fans.supply.setpoint_v",
                    "Nawiew · wartość zadana",
                    "V",
                    "zone1.fans",
                    "zone1",
                    1,
                    "setpoints.supply_voltage",
                ),
                HistorySeriesSpec(
                    "zone1.fans.extract.setpoint_v",
                    "Wyciąg · wartość zadana",
                    "V",
                    "zone1.fans",
                    "zone1",
                    1,
                    "setpoints.extract_voltage",
                ),
                HistorySeriesSpec(
                    "zone1.fans.supply.rpm",
                    "Nawiew · prędkość",
                    "RPM",
                    "zone1.fans",
                    "zone1",
                    0,
                    "tacho.supply.rpm",
                ),
                HistorySeriesSpec(
                    "zone1.fans.extract.rpm",
                    "Wyciąg · prędkość",
                    "RPM",
                    "zone1.fans",
                    "zone1",
                    0,
                    "tacho.extract.rpm",
                ),
                HistorySeriesSpec(
                    "zone1.fans.supply.frequency_hz",
                    "Nawiew · TACHO",
                    "Hz",
                    "zone1.fans",
                    "zone1",
                    1,
                    "tacho.supply.frequency_hz",
                ),
                HistorySeriesSpec(
                    "zone1.fans.extract.frequency_hz",
                    "Wyciąg · TACHO",
                    "Hz",
                    "zone1.fans",
                    "zone1",
                    1,
                    "tacho.extract.frequency_hz",
                ),
                HistorySeriesSpec(
                    "zone1.duct.supply.temperature",
                    "Kanał nawiewny · temperatura",
                    "°C",
                    "zone1.duct",
                    "zone1",
                    1,
                    zigbee_role="supply",
                ),
                HistorySeriesSpec(
                    "zone1.duct.extract.temperature",
                    "Kanał wywiewny · temperatura",
                    "°C",
                    "zone1.duct",
                    "zone1",
                    1,
                    zigbee_role="extract",
                ),
                HistorySeriesSpec(
                    "zone2.aero.humidity",
                    "AERO · wilgotność",
                    "%",
                    "zone2.aero",
                    "zone2",
                    1,
                    "aero_bus.telemetry.humidity_percent",
                ),
                HistorySeriesSpec(
                    "zone2.aero.supply_temperature",
                    "AERO · temperatura nawiewu",
                    "°C",
                    "zone2.aero",
                    "zone2",
                    1,
                    "aero_bus.telemetry.supply_temperature_celsius",
                ),
                HistorySeriesSpec(
                    "zone2.aero.extract_temperature",
                    "AERO · temperatura wywiewu",
                    "°C",
                    "zone2.aero",
                    "zone2",
                    1,
                    "aero_bus.telemetry.extract_temperature_celsius",
                ),
                HistorySeriesSpec(
                    "zone2.aero.outdoor_temperature",
                    "AERO · temperatura zewnętrzna",
                    "°C",
                    "zone2.aero",
                    "zone2",
                    1,
                    "aero_bus.telemetry.outdoor_temperature_celsius",
                ),
                HistorySeriesSpec(
                    "zone2.aero.fan1_percent",
                    "AERO · wentylator 1",
                    "%",
                    "zone2.aero",
                    "zone2",
                    0,
                    "aero_bus.telemetry.fan_1_percent",
                ),
                HistorySeriesSpec(
                    "zone2.aero.fan2_percent",
                    "AERO · wentylator 2",
                    "%",
                    "zone2.aero",
                    "zone2",
                    0,
                    "aero_bus.telemetry.fan_2_percent",
                ),
            ]
        )
        return {spec.id: spec for spec in specs}
