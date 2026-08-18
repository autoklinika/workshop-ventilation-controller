from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from ventilation_core.domain.zigbee import (
    ZigbeeCapability,
    ZigbeeInventoryDevice,
    ZigbeePairingState,
    ZigbeeSensorListItem,
)
from ventilation_core.infrastructure.zigbee_managed_monitor import ManagedReliableZigbeeMqttMonitor
from ventilation_core.infrastructure.zigbee_reliable_monitor import parse_availability_payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def parse_published_capabilities(exposes: Any) -> tuple[ZigbeeCapability, ...]:
    """Flatten Zigbee2MQTT exposes to values present in published device state.

    Zigbee2MQTT access bit 1 means the property appears in the published state.
    Configuration-only exposes are intentionally omitted: this screen describes
    what the device reports, not what the UI could configure or control.
    """

    if not isinstance(exposes, list):
        return ()

    capabilities: list[ZigbeeCapability] = []
    seen: set[tuple[str, str | None]] = set()

    def visit(item: Any, inherited_endpoint: str | None = None) -> None:
        if not isinstance(item, dict):
            return
        endpoint = _text(item.get("endpoint")) or inherited_endpoint
        features = item.get("features")
        if isinstance(features, list) and features:
            for feature in features:
                visit(feature, endpoint)
            return

        access = item.get("access")
        if isinstance(access, bool) or not isinstance(access, int) or not access & 0b001:
            return
        if item.get("category") == "config":
            return
        property_name = _text(item.get("property"))
        name = _text(item.get("name"))
        if property_name is None or name is None:
            return
        key = (property_name, endpoint)
        if key in seen:
            return
        seen.add(key)

        raw_values = item.get("values")
        values = tuple(str(value) for value in raw_values) if isinstance(raw_values, list) else ()
        capabilities.append(
            ZigbeeCapability(
                property=property_name,
                name=name,
                label=_text(item.get("label")) or name.replace("_", " ").title(),
                value_type=_text(item.get("type")) or "unknown",
                unit=_text(item.get("unit")),
                endpoint=endpoint,
                category=_text(item.get("category")),
                description=_text(item.get("description")),
                access=access,
                value_min=_number(item.get("value_min")),
                value_max=_number(item.get("value_max")),
                value_step=_number(item.get("value_step")),
                values=values,
            )
        )

    for expose in exposes:
        visit(expose)
    return tuple(capabilities)


def parse_bridge_devices_with_capabilities(payload: Any) -> tuple[ZigbeeInventoryDevice, ...]:
    if not isinstance(payload, list):
        raise ValueError("bridge/devices payload must be a JSON array")
    inventory: list[ZigbeeInventoryDevice] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        ieee = _text(item.get("ieee_address"))
        if ieee is None:
            continue
        friendly_name = _text(item.get("friendly_name")) or ieee
        device_type = _text(item.get("type")) or "Unknown"
        definition = item.get("definition")
        if not isinstance(definition, dict):
            definition = {}
        inventory.append(
            ZigbeeInventoryDevice(
                ieee_address=ieee,
                friendly_name=friendly_name,
                device_type=device_type,
                supported=item.get("supported") is True,
                disabled=item.get("disabled") is True,
                model=_text(definition.get("model")) or _text(item.get("model_id")),
                vendor=_text(definition.get("vendor")),
                description=_text(definition.get("description")) or _text(item.get("description")),
                power_source=_text(item.get("power_source")),
                interview_state=_text(item.get("interview_state")),
                capabilities=parse_published_capabilities(definition.get("exposes")),
            )
        )
    return tuple(inventory)


class CapabilityManagedZigbeeMqttMonitor(ManagedReliableZigbeeMqttMonitor):
    """Core-owned pairing, capability and generic sensor telemetry boundary."""

    def __init__(self, config, *, role_store) -> None:
        self._sensor_list_by_ieee: dict[str, ZigbeeSensorListItem] = {}
        self._generic_topic_to_ieee: dict[str, str] = {}
        self._generic_availability_to_ieee: dict[str, str] = {}
        super().__init__(config, role_store=role_store)

    def state(self):
        state = super().state()
        with self._lock:
            inventory_order = {
                item.ieee_address: index
                for index, item in enumerate(self._state.inventory)
                if not item.is_coordinator
            }
            items = tuple(self._sensor_list_by_ieee.values())
        normalized = tuple(
            replace(item, role=self.role_for_ieee(item.ieee_address))
            for item in sorted(
                items,
                key=lambda item: (
                    inventory_order.get(item.ieee_address, 10**9),
                    item.friendly_name.lower(),
                ),
            )
        )
        return replace(state, sensor_list=normalized)

    def acknowledge_pairing(self, ieee_address: str) -> dict[str, Any]:
        if not isinstance(ieee_address, str) or not ieee_address.strip():
            raise ValueError("Zigbee pairing IEEE address must be a non-empty string")
        ieee = ieee_address.strip()
        with self._lock:
            pairing = self._state.pairing
            if pairing is None:
                raise RuntimeError("No Zigbee pairing result is awaiting acknowledgement")
            if pairing.ieee_address != ieee:
                raise ValueError("Zigbee pairing acknowledgement does not match current device")
            self._state = replace(self._state, pairing=replace(pairing, acknowledged=True))
        return {"status": "ok", "data": {"ieee_address": ieee, "acknowledged": True}}

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        super()._on_connect(client, userdata, flags, reason_code, properties)
        with self._lock:
            connected = self._state.connected is True
            topics = tuple(
                sorted(set(self._generic_topic_to_ieee) | set(self._generic_availability_to_ieee))
            )
        if connected and topics:
            client.subscribe([(topic, 0) for topic in topics])

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        topic = str(message.topic)
        with self._lock:
            availability_ieee = self._generic_availability_to_ieee.get(topic)
            state_ieee = self._generic_topic_to_ieee.get(topic)
        if availability_ieee is not None:
            self._handle_generic_availability(availability_ieee, message.payload)
        elif state_ieee is not None:
            self._handle_generic_payload(state_ieee, message.payload)
        super()._on_message(client, userdata, message)

    def _handle_bridge_message(self, topic: str, raw_payload: bytes) -> None:
        super()._handle_bridge_message(topic, raw_payload)
        base = self._state.base_topic
        if topic == f"{base}/bridge/devices":
            self._handle_capability_inventory(raw_payload)
        elif topic == f"{base}/bridge/event":
            self._handle_pairing_event(raw_payload)

    def _handle_capability_inventory(self, raw_payload: bytes) -> None:
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
            inventory = parse_bridge_devices_with_capabilities(payload)
        except Exception:
            return

        with self._lock:
            pairing = self._state.pairing
            if pairing is not None:
                matched = next(
                    (device for device in inventory if device.ieee_address == pairing.ieee_address),
                    None,
                )
                if matched is not None:
                    pairing = replace(
                        pairing,
                        friendly_name=matched.friendly_name,
                        supported=matched.supported,
                        model=matched.model or pairing.model,
                        vendor=matched.vendor or pairing.vendor,
                        description=matched.description or pairing.description,
                        capabilities=matched.capabilities,
                    )

            old_topics = set(self._generic_topic_to_ieee) | set(self._generic_availability_to_ieee)
            previous = dict(self._sensor_list_by_ieee)
            sensor_rows: dict[str, ZigbeeSensorListItem] = {}
            state_topics: dict[str, str] = {}
            availability_topics: dict[str, str] = {}
            base = self._state.base_topic
            for device in inventory:
                if device.is_coordinator:
                    continue
                topic = f"{base}/{device.friendly_name}"
                old = previous.get(device.ieee_address)
                if old is None:
                    row = ZigbeeSensorListItem(
                        ieee_address=device.ieee_address,
                        friendly_name=device.friendly_name,
                        topic=topic,
                        model=device.model,
                        vendor=device.vendor,
                    )
                else:
                    row = replace(
                        old,
                        friendly_name=device.friendly_name,
                        topic=topic,
                        model=device.model,
                        vendor=device.vendor,
                    )
                sensor_rows[device.ieee_address] = row
                state_topics[topic] = device.ieee_address
                availability_topics[f"{topic}/availability"] = device.ieee_address

            self._sensor_list_by_ieee = sensor_rows
            self._generic_topic_to_ieee = state_topics
            self._generic_availability_to_ieee = availability_topics
            new_topics = set(state_topics) | set(availability_topics)
            connected = self._state.connected is True
            self._state = replace(
                self._state,
                inventory=inventory,
                inventory_updated_at=_now_iso(),
                pairing=pairing,
            )

        if connected:
            for topic in sorted(old_topics - new_topics):
                self._client.unsubscribe(topic)
            additions = sorted(new_topics - old_topics)
            if additions:
                self._client.subscribe([(topic, 0) for topic in additions])

    def _handle_generic_payload(self, ieee_address: str, raw_payload: bytes) -> None:
        received_at = _now_iso()
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("device payload must be a JSON object")
        except Exception as exc:
            with self._lock:
                previous = self._sensor_list_by_ieee.get(ieee_address)
                if previous is not None:
                    self._sensor_list_by_ieee[ieee_address] = replace(
                        previous,
                        parse_errors=previous.parse_errors + 1,
                        last_error=f"{type(exc).__name__}: {exc}",
                    )
            return

        with self._lock:
            previous = self._sensor_list_by_ieee.get(ieee_address)
            if previous is None:
                return
            changes: dict[str, Any] = {
                "last_message_at": received_at,
                "messages": previous.messages + 1,
                "last_error": None,
            }
            errors: list[str] = []

            def numeric(source: str, target: str, minimum: float | None = None, maximum: float | None = None, integer: bool = False) -> None:
                if source not in payload:
                    return
                value = _number(payload[source])
                if value is None or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                    errors.append(f"invalid {source}")
                    return
                changes[target] = int(value) if integer else value

            numeric("temperature", "temperature_celsius")
            numeric("humidity", "humidity_percent", 0.0, 100.0)
            numeric("battery", "battery_percent", 0.0, 100.0)
            numeric("voltage", "voltage_mv", 0.0)
            numeric("linkquality", "linkquality", 0.0, 255.0, integer=True)
            if "last_seen" in payload:
                last_seen = payload.get("last_seen")
                if last_seen is None or isinstance(last_seen, str):
                    changes["last_seen"] = last_seen
                else:
                    errors.append("invalid last_seen")
            if errors:
                changes["parse_errors"] = previous.parse_errors + 1
                changes["last_error"] = ", ".join(errors)

            self._sensor_list_by_ieee[ieee_address] = replace(previous, **changes)
            self._state = replace(self._state, last_message_at=received_at)

    def _handle_generic_availability(self, ieee_address: str, raw_payload: bytes) -> None:
        with self._lock:
            previous = self._sensor_list_by_ieee.get(ieee_address)
        if previous is None:
            return
        try:
            available = parse_availability_payload(raw_payload)
        except Exception as exc:
            with self._lock:
                current = self._sensor_list_by_ieee.get(ieee_address)
                if current is not None:
                    self._sensor_list_by_ieee[ieee_address] = replace(
                        current,
                        parse_errors=current.parse_errors + 1,
                        last_error=f"availability: {exc}",
                    )
            return
        with self._lock:
            current = self._sensor_list_by_ieee.get(ieee_address)
            if current is not None:
                self._sensor_list_by_ieee[ieee_address] = replace(current, available=available)

    def _handle_pairing_event(self, raw_payload: bytes) -> None:
        try:
            payload = json.loads(raw_payload.decode("utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        event_type = payload.get("type")
        data = payload.get("data")
        if not isinstance(data, dict):
            return
        ieee = _text(data.get("ieee_address"))
        friendly_name = _text(data.get("friendly_name")) or ieee
        if ieee is None or friendly_name is None:
            return

        status: str | None = None
        supported: bool | None = None
        definition: dict[str, Any] = {}
        if event_type == "device_joined":
            status = "joined"
        elif event_type == "device_interview":
            raw_status = data.get("status")
            if raw_status in {"started", "successful", "failed"}:
                status = str(raw_status)
            supported = data.get("supported") if isinstance(data.get("supported"), bool) else None
            if isinstance(data.get("definition"), dict):
                definition = data["definition"]
        if status is None:
            return

        pairing = ZigbeePairingState(
            status=status,
            ieee_address=ieee,
            friendly_name=friendly_name,
            event_at=_now_iso(),
            supported=supported,
            model=_text(definition.get("model")),
            vendor=_text(definition.get("vendor")),
            description=_text(definition.get("description")),
            capabilities=parse_published_capabilities(definition.get("exposes")),
            acknowledged=False,
        )
        with self._lock:
            current = self._state.pairing
            if current is not None and current.ieee_address == ieee:
                pairing = replace(
                    pairing,
                    model=pairing.model or current.model,
                    vendor=pairing.vendor or current.vendor,
                    description=pairing.description or current.description,
                    capabilities=pairing.capabilities or current.capabilities,
                )
            self._state = replace(self._state, pairing=pairing)

        with self._lock:
            matched = next(
                (device for device in self._state.inventory if device.ieee_address == ieee),
                None,
            )
            if matched is not None:
                current = self._state.pairing
                if current is not None and current.ieee_address == ieee:
                    self._state = replace(
                        self._state,
                        pairing=replace(
                            current,
                            friendly_name=matched.friendly_name,
                            supported=matched.supported,
                            model=matched.model or current.model,
                            vendor=matched.vendor or current.vendor,
                            description=matched.description or current.description,
                            capabilities=matched.capabilities or current.capabilities,
                        ),
                    )
