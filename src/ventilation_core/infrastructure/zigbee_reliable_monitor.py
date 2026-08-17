from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

from ventilation_core.infrastructure.zigbee_mqtt_monitor import ZigbeeMqttMonitor


LOGGER = logging.getLogger(__name__)


def parse_availability_payload(payload: bytes) -> bool:
    """Decode Zigbee2MQTT availability payload.

    Zigbee2MQTT 2.x publishes retained JSON payloads such as
    {"state":"online"}. Plain text online/offline remains accepted for
    compatibility with older deployments and already captured test fixtures.
    """
    raw = payload.decode("utf-8", errors="strict").strip()
    if not raw:
        raise ValueError("empty Zigbee availability payload")

    value: Any
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    else:
        if isinstance(decoded, dict):
            value = decoded.get("state")
        else:
            value = decoded

    if not isinstance(value, str):
        raise ValueError("Zigbee availability state must be a string")
    state = value.strip().lower()
    if state == "online":
        return True
    if state == "offline":
        return False
    raise ValueError(f"unsupported Zigbee availability state: {value!r}")


class ReliableZigbeeMqttMonitor(ZigbeeMqttMonitor):
    """Zigbee monitor with current Zigbee2MQTT availability semantics."""

    def _handle_availability(self, role: str, payload: bytes) -> None:
        try:
            available = parse_availability_payload(payload)
        except Exception as exc:
            LOGGER.warning("Unexpected Zigbee availability payload for %s: %s", role, exc)
            return

        with self._lock:
            self._devices[role] = replace(
                self._devices[role],
                available=available,
            )
            self._state = replace(self._state, devices=self._ordered_devices())
