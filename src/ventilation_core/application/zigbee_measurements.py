from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from ventilation_core.domain.zigbee import ZigbeeMqttState, ZigbeeTemperatureSensorState


DEFAULT_ZIGBEE_STALE_SECONDS = 14400.0


@dataclass(frozen=True)
class ZigbeeTemperatureMeasurement:
    role: str
    temperature_celsius: float | None
    usable: bool
    stale: bool
    age_seconds: float | None
    source_timestamp: str | None
    reason: str


def timestamp_age_seconds(value: str | None, *, now_utc: datetime) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = _aware_utc(now_utc)
    return max(0.0, (now - parsed.astimezone(timezone.utc)).total_seconds())


def normalize_zigbee_temperature(
    state: ZigbeeMqttState | None,
    role: str,
    *,
    now_utc: datetime,
    stale_seconds: float = DEFAULT_ZIGBEE_STALE_SECONDS,
) -> ZigbeeTemperatureMeasurement:
    """Return one deterministic role-based temperature measurement.

    This function is the shared read-only interpretation used by both alerts and
    the Control Engine.  It never sends MQTT commands and never changes Zigbee
    state.  A retained payload is accepted only if its measurement timestamp can
    be proven fresh enough for the configured stale window.
    """

    now = _aware_utc(now_utc)
    if not isinstance(role, str) or not role.strip():
        raise ValueError("Zigbee temperature role must be non-empty text")
    if not isinstance(stale_seconds, (int, float)) or isinstance(stale_seconds, bool):
        raise ValueError("Zigbee stale threshold must be numeric")
    if not math.isfinite(float(stale_seconds)) or float(stale_seconds) <= 0.0:
        raise ValueError("Zigbee stale threshold must be positive and finite")

    if state is None:
        return _missing(role, "ZIGBEE_STATE_UNAVAILABLE")
    if state.running is not True:
        return _missing(role, "ZIGBEE_MONITOR_NOT_RUNNING")
    if state.connected is not True:
        return _missing(role, "ZIGBEE_MQTT_DISCONNECTED")
    if state.bridge_online is False:
        return _missing(role, "ZIGBEE_BRIDGE_OFFLINE")

    device = _device_for_role(state, role)
    if device is None:
        return _missing(role, "ZIGBEE_ROLE_UNASSIGNED")
    if device.available is False:
        return _from_device(device, usable=False, stale=False, age=None, timestamp=None, reason="ZIGBEE_DEVICE_OFFLINE")

    value = device.temperature_celsius
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return _from_device(device, usable=False, stale=False, age=None, timestamp=None, reason="TEMPERATURE_UNAVAILABLE")

    timestamp = device.last_seen or device.last_message_at
    age = timestamp_age_seconds(timestamp, now_utc=now)
    if age is None:
        return _from_device(
            device,
            usable=False,
            stale=False,
            age=None,
            timestamp=timestamp,
            reason="TEMPERATURE_TIMESTAMP_UNAVAILABLE",
        )
    if age > float(stale_seconds):
        return _from_device(
            device,
            usable=False,
            stale=True,
            age=age,
            timestamp=timestamp,
            reason="TEMPERATURE_STALE",
        )
    return _from_device(
        device,
        usable=True,
        stale=False,
        age=age,
        timestamp=timestamp,
        reason="OK",
    )


def _device_for_role(state: ZigbeeMqttState, role: str) -> ZigbeeTemperatureSensorState | None:
    matches = [device for device in state.devices if device.role == role]
    if len(matches) > 1:
        # Role uniqueness is a core invariant. Treat corrupted state as unusable
        # instead of picking one device non-deterministically.
        return None
    return matches[0] if matches else None


def _missing(role: str, reason: str) -> ZigbeeTemperatureMeasurement:
    return ZigbeeTemperatureMeasurement(
        role=role,
        temperature_celsius=None,
        usable=False,
        stale=False,
        age_seconds=None,
        source_timestamp=None,
        reason=reason,
    )


def _from_device(
    device: ZigbeeTemperatureSensorState,
    *,
    usable: bool,
    stale: bool,
    age: float | None,
    timestamp: str | None,
    reason: str,
) -> ZigbeeTemperatureMeasurement:
    return ZigbeeTemperatureMeasurement(
        role=device.role,
        temperature_celsius=(
            None if device.temperature_celsius is None else float(device.temperature_celsius)
        ),
        usable=usable,
        stale=stale,
        age_seconds=age,
        source_timestamp=timestamp,
        reason=reason,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Zigbee measurement clock must be timezone-aware")
    return value.astimezone(timezone.utc)
