from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from ventilation_core.domain.zigbee import (
    ZigbeeCapability,
    ZigbeeInventoryDevice,
    ZigbeePairingState,
)
from ventilation_core.infrastructure.zigbee_managed_monitor import ManagedReliableZigbeeMqttMonitor


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


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
            # Composite exposes are containers. Report their published leaf
            # values, not the synthetic parent plus the same child values.
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
    """Managed Zigbee boundary with core-owned pairing recognition/capabilities."""

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
            self._state = replace(
                self._state,
                inventory=inventory,
                inventory_updated_at=_now_iso(),
                pairing=pairing,
            )

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

        # bridge/devices can arrive before/after interview event. Hydrate from the
        # authoritative inventory immediately if it is already available.
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
