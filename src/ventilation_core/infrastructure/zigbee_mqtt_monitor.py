from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from ventilation_core.domain.zigbee import (
    ZigbeeMqttState,
    ZigbeeTemperatureSensorState,
)


LOGGER = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ZigbeeDeviceConfig:
    role: str
    friendly_name: str
    ieee_address: str | None = None

    def __post_init__(self) -> None:
        if not self.role.strip():
            raise ValueError("Zigbee device role cannot be empty")
        if not self.friendly_name.strip():
            raise ValueError("Zigbee friendly name cannot be empty")


@dataclass(frozen=True)
class ZigbeeMqttConfig:
    broker_host: str = "127.0.0.1"
    broker_port: int = 1883
    base_topic: str = "zigbee2mqtt"
    client_id: str = "ventilation-core-zigbee"
    keepalive_seconds: int = 60
    reconnect_min_seconds: int = 1
    reconnect_max_seconds: int = 30
    devices: tuple[ZigbeeDeviceConfig, ...] = ()

    def __post_init__(self) -> None:
        if not self.broker_host.strip():
            raise ValueError("MQTT broker host cannot be empty")
        if not 1 <= self.broker_port <= 65535:
            raise ValueError("MQTT broker port must be in range 1..65535")
        if not self.base_topic.strip("/ "):
            raise ValueError("MQTT base topic cannot be empty")
        if self.keepalive_seconds <= 0:
            raise ValueError("MQTT keepalive must be positive")
        if self.reconnect_min_seconds <= 0 or self.reconnect_max_seconds < self.reconnect_min_seconds:
            raise ValueError("Invalid MQTT reconnect delay configuration")
        if not self.devices:
            raise ValueError("At least one Zigbee device is required")
        roles = [device.role for device in self.devices]
        names = [device.friendly_name for device in self.devices]
        if len(set(roles)) != len(roles):
            raise ValueError("Zigbee device roles must be unique")
        if len(set(names)) != len(names):
            raise ValueError("Zigbee friendly names must be unique")


def _optional_finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def merge_device_payload(
    previous: ZigbeeTemperatureSensorState,
    payload: dict[str, Any],
    *,
    received_at: str,
) -> ZigbeeTemperatureSensorState:
    changes: dict[str, Any] = {
        "last_message_at": received_at,
        "messages": previous.messages + 1,
        "last_error": None,
    }

    if "temperature" in payload:
        changes["temperature_celsius"] = _optional_finite_number(
            payload["temperature"], "temperature"
        )
    if "battery" in payload:
        battery = _optional_finite_number(payload["battery"], "battery")
        if not 0.0 <= battery <= 100.0:
            raise ValueError("battery must be in range 0..100")
        changes["battery_percent"] = battery
    if "linkquality" in payload:
        linkquality = _optional_finite_number(payload["linkquality"], "linkquality")
        if not 0.0 <= linkquality <= 255.0:
            raise ValueError("linkquality must be in range 0..255")
        changes["linkquality"] = int(linkquality)
    if "last_seen" in payload:
        last_seen = payload["last_seen"]
        if last_seen is not None and not isinstance(last_seen, str):
            raise ValueError("last_seen must be a string or null")
        changes["last_seen"] = last_seen

    return replace(previous, **changes)


class ZigbeeMqttMonitor:
    """Read-only MQTT monitor for Zigbee2MQTT temperature sensors.

    The monitor never controls Zigbee devices. MQTT/network failures are kept
    inside this adapter and reflected in state; they must not block fan control.
    """

    def __init__(self, config: ZigbeeMqttConfig) -> None:
        self._config = config
        self._lock = RLock()
        self._closed = False
        base_topic = config.base_topic.strip("/")
        self._devices = {
            device.role: ZigbeeTemperatureSensorState(
                role=device.role,
                friendly_name=device.friendly_name,
                ieee_address=device.ieee_address,
                topic=f"{base_topic}/{device.friendly_name}",
            )
            for device in config.devices
        }
        self._topic_to_role = {
            device.topic: role for role, device in self._devices.items()
        }
        self._availability_to_role = {
            f"{device.topic}/availability": role for role, device in self._devices.items()
        }
        self._state = ZigbeeMqttState(
            broker_host=config.broker_host,
            broker_port=config.broker_port,
            base_topic=base_topic,
            devices=self._ordered_devices(),
        )

        # Imported lazily so a missing optional runtime package cannot make
        # ventilation_core.main itself unimportable. Deployment installs the
        # Debian python3-paho-mqtt package before enabling this monitor.
        import paho.mqtt.client as mqtt

        self._mqtt = mqtt
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
            protocol=mqtt.MQTTv311,
        )
        self._client.on_connect = self._on_connect
        self._client.on_connect_fail = self._on_connect_fail
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(
            min_delay=config.reconnect_min_seconds,
            max_delay=config.reconnect_max_seconds,
        )
        self._client.connect_async(
            config.broker_host,
            port=config.broker_port,
            keepalive=config.keepalive_seconds,
        )
        rc = self._client.loop_start()
        if rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Unable to start MQTT network loop: {rc}")
        with self._lock:
            self._state = replace(self._state, running=True)

    def state(self) -> ZigbeeMqttState:
        with self._lock:
            return replace(self._state, devices=self._ordered_devices())

    def health_check(self) -> None:
        # Paho's threaded network loop handles reconnects automatically. This
        # application-level health check intentionally does not restart or block.
        with self._lock:
            if self._closed:
                return
            self._state = replace(
                self._state,
                running=True,
                devices=self._ordered_devices(),
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._client.disconnect()
        except Exception:
            LOGGER.exception("Failed to disconnect Zigbee MQTT client cleanly")
        try:
            self._client.loop_stop()
        finally:
            with self._lock:
                self._state = replace(
                    self._state,
                    running=False,
                    connected=False,
                    disconnected_at=_now_iso(),
                    devices=self._ordered_devices(),
                )

    def _on_connect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        if reason_code != 0:
            self._set_connection_error(f"MQTT CONNACK rejected: {reason_code}")
            return
        subscriptions = [
            (topic, 0)
            for topic in (*self._topic_to_role.keys(), *self._availability_to_role.keys())
        ]
        result, _mid = client.subscribe(subscriptions)
        if result != self._mqtt.MQTT_ERR_SUCCESS:
            self._set_connection_error(f"MQTT subscribe failed: {result}")
            return
        now = _now_iso()
        with self._lock:
            self._state = replace(
                self._state,
                running=True,
                connected=True,
                connected_at=now,
                last_error=None,
                devices=self._ordered_devices(),
            )
        LOGGER.info(
            "Zigbee MQTT connected to %s:%d; subscribed devices=%s",
            self._config.broker_host,
            self._config.broker_port,
            tuple(device.friendly_name for device in self._devices.values()),
        )

    def _on_connect_fail(self, client: Any, userdata: Any) -> None:
        self._set_connection_error("MQTT connection attempt failed")

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        now = _now_iso()
        error = None if self._closed else f"MQTT disconnected: {reason_code}"
        with self._lock:
            self._state = replace(
                self._state,
                connected=False,
                disconnected_at=now,
                last_error=error,
                devices=self._ordered_devices(),
            )

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        topic = str(message.topic)
        if topic in self._availability_to_role:
            self._handle_availability(
                self._availability_to_role[topic],
                message.payload,
            )
            return

        role = self._topic_to_role.get(topic)
        if role is None:
            return
        received_at = _now_iso()
        try:
            raw = message.payload.decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("device payload must be a JSON object")
            with self._lock:
                previous = self._devices[role]
                updated = merge_device_payload(
                    previous,
                    payload,
                    received_at=received_at,
                )
                self._devices[role] = updated
                self._state = replace(
                    self._state,
                    last_message_at=received_at,
                    last_error=None,
                    devices=self._ordered_devices(),
                )
        except Exception as exc:
            with self._lock:
                previous = self._devices[role]
                self._devices[role] = replace(
                    previous,
                    parse_errors=previous.parse_errors + 1,
                    last_error=f"{type(exc).__name__}: {exc}",
                )
                self._state = replace(
                    self._state,
                    last_error=f"Invalid MQTT payload for {previous.friendly_name}: {exc}",
                    devices=self._ordered_devices(),
                )
            LOGGER.warning("Invalid Zigbee MQTT payload on %s: %s", topic, exc)

    def _handle_availability(self, role: str, payload: bytes) -> None:
        value = payload.decode("utf-8", errors="replace").strip().lower()
        if value not in {"online", "offline"}:
            LOGGER.warning("Unexpected Zigbee availability payload for %s: %r", role, value)
            return
        with self._lock:
            self._devices[role] = replace(
                self._devices[role],
                available=value == "online",
            )
            self._state = replace(self._state, devices=self._ordered_devices())

    def _set_connection_error(self, error: str) -> None:
        with self._lock:
            self._state = replace(
                self._state,
                connected=False,
                last_error=error,
                devices=self._ordered_devices(),
            )
        LOGGER.warning("Zigbee MQTT: %s", error)

    def _ordered_devices(self) -> tuple[ZigbeeTemperatureSensorState, ...]:
        return tuple(self._devices[device.role] for device in self._config.devices)
