from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Protocol

from ventilation_core.application.alerting_service import AlertingVentilationService
from ventilation_core.domain.alerts import AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity, CoreState
from ventilation_core.domain.zigbee import ZigbeeMqttState


LOGGER = logging.getLogger(__name__)


class ZigbeeMonitor(Protocol):
    def state(self) -> ZigbeeMqttState: ...
    def health_check(self) -> None: ...
    def permit_join(self, seconds: int) -> dict[str, Any]: ...
    def remove_device(self, device_id: str) -> dict[str, Any]: ...
    def rename_device(self, device_id: str, new_name: str) -> dict[str, Any]: ...
    def assign_role(self, device_id: str, role: str | None) -> dict[str, Any]: ...
    def acknowledge_pairing(self, ieee_address: str) -> dict[str, Any]: ...
    def close(self) -> None: ...


def _age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(
        0.0,
        (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds(),
    )


class ZigbeeAlertingVentilationService(AlertingVentilationService):
    """Alerting service extended with Zigbee telemetry and narrow management."""

    def __init__(
        self,
        *args: object,
        zigbee: ZigbeeMonitor | None = None,
        zigbee_low_battery_percent: float = 20.0,
        zigbee_stale_seconds: float = 14400.0,
        **kwargs: object,
    ) -> None:
        if not 0.0 <= zigbee_low_battery_percent <= 100.0:
            raise ValueError("Zigbee low battery threshold must be in range 0..100")
        if zigbee_stale_seconds <= 0:
            raise ValueError("Zigbee stale threshold must be positive")
        self._zigbee = zigbee
        self._zigbee_low_battery_percent = float(zigbee_low_battery_percent)
        self._zigbee_stale_seconds = float(zigbee_stale_seconds)
        super().__init__(*args, **kwargs)

    def state(self) -> CoreState:
        return self._with_zigbee(super().state())

    def health_check(self) -> CoreState:
        if self._zigbee is not None:
            try:
                self._zigbee.health_check()
            except Exception:
                LOGGER.exception("Zigbee monitor health check failed")
        return self._with_zigbee(super().health_check())

    def set_manual(self, supply_voltage: float, extract_voltage: float) -> CoreState:
        return self._with_zigbee(super().set_manual(supply_voltage, extract_voltage))

    def stop(self) -> CoreState:
        return self._with_zigbee(super().stop())

    def zigbee_permit_join(self, seconds: int) -> dict[str, Any]:
        if self._zigbee is None:
            raise RuntimeError("Zigbee is not configured")
        return self._zigbee.permit_join(seconds)

    def zigbee_remove_device(self, device_id: str) -> dict[str, Any]:
        if self._zigbee is None:
            raise RuntimeError("Zigbee is not configured")
        return self._zigbee.remove_device(device_id)

    def zigbee_rename_device(self, device_id: str, new_name: str) -> dict[str, Any]:
        if self._zigbee is None:
            raise RuntimeError("Zigbee is not configured")
        return self._zigbee.rename_device(device_id, new_name)

    def zigbee_assign_role(self, device_id: str, role: str | None) -> dict[str, Any]:
        if self._zigbee is None:
            raise RuntimeError("Zigbee is not configured")
        return self._zigbee.assign_role(device_id, role)

    def zigbee_acknowledge_pairing(self, ieee_address: str) -> dict[str, Any]:
        if self._zigbee is None:
            raise RuntimeError("Zigbee is not configured")
        return self._zigbee.acknowledge_pairing(ieee_address)

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._zigbee is not None:
                try:
                    self._zigbee.close()
                except Exception:
                    LOGGER.exception("Failed to close Zigbee MQTT monitor")

    def _with_zigbee(self, state: CoreState) -> CoreState:
        if self._zigbee is None:
            return state
        try:
            return replace(state, zigbee=self._zigbee.state())
        except Exception:
            LOGGER.exception("Unable to read Zigbee state")
            return state

    def _extra_alert_signals(self, state: CoreState) -> list[AlertSignal]:
        if self._zigbee is None:
            return []
        try:
            zigbee = self._zigbee.state()
        except Exception as exc:
            return [
                AlertSignal(
                    key="zigbee:mqtt",
                    code=AlarmCode.ZIGBEE_MQTT_DISCONNECTED,
                    source="zigbee",
                    severity=AlarmSeverity.WARNING,
                    message="Zigbee: stan klienta MQTT jest niedostępny",
                    detail=str(exc),
                )
            ]

        signals: list[AlertSignal] = []
        if (
            zigbee.running is True
            and zigbee.connected is not True
            and (zigbee.disconnected_at is not None or bool(zigbee.last_error))
        ):
            signals.append(
                AlertSignal(
                    key="zigbee:mqtt",
                    code=AlarmCode.ZIGBEE_MQTT_DISCONNECTED,
                    source="zigbee",
                    severity=AlarmSeverity.WARNING,
                    message="Zigbee: brak połączenia z lokalnym brokerem MQTT",
                    detail=zigbee.last_error or "MQTT disconnected",
                )
            )

        if zigbee.connected is True and zigbee.bridge_online is False:
            signals.append(
                AlertSignal(
                    key="zigbee:bridge",
                    code=AlarmCode.ZIGBEE_BRIDGE_OFFLINE,
                    source="zigbee",
                    severity=AlarmSeverity.WARNING,
                    message="Zigbee2MQTT jest offline",
                    detail="Broker MQTT działa, ale retained bridge/state zgłasza offline",
                )
            )

        inventory_ready = zigbee.inventory_updated_at is not None
        for device in zigbee.devices:
            source = f"zigbee:{device.friendly_name}"
            present = True
            if inventory_ready:
                present = any(
                    (
                        device.ieee_address is not None
                        and item.ieee_address == device.ieee_address
                    )
                    or item.friendly_name == device.friendly_name
                    for item in zigbee.inventory
                    if not item.is_coordinator
                )

            if not present or device.available is False:
                signals.append(
                    AlertSignal(
                        key=f"zigbee:device:{device.role}:offline",
                        code=AlarmCode.ZIGBEE_DEVICE_OFFLINE,
                        source=source,
                        severity=AlarmSeverity.WARNING,
                        message=f"Zigbee {device.friendly_name}: urządzenie niedostępne",
                        detail=(
                            "Urządzenie nie występuje w bridge/devices"
                            if not present
                            else "Zigbee2MQTT availability=offline"
                        ),
                    )
                )
                continue

            age = _age_seconds(device.last_seen)
            age_source = "last_seen"
            if age is None:
                age = _age_seconds(device.last_message_at)
                age_source = "last_message_at"
            if (
                device.messages > 0
                and age is not None
                and age > self._zigbee_stale_seconds
            ):
                signals.append(
                    AlertSignal(
                        key=f"zigbee:device:{device.role}:stale",
                        code=AlarmCode.ZIGBEE_DEVICE_DATA_STALE,
                        source=source,
                        severity=AlarmSeverity.WARNING,
                        message=f"Zigbee {device.friendly_name}: brak świeżych danych",
                        detail=(
                            f"Wiek ostatniego pomiaru ({age_source}) {int(age)} s; "
                            f"próg {int(self._zigbee_stale_seconds)} s"
                        ),
                    )
                )

            battery = device.battery_percent
            if battery is not None and battery <= self._zigbee_low_battery_percent:
                signals.append(
                    AlertSignal(
                        key=f"zigbee:device:{device.role}:battery",
                        code=AlarmCode.ZIGBEE_LOW_BATTERY,
                        source=source,
                        severity=AlarmSeverity.WARNING,
                        message=f"Zigbee {device.friendly_name}: niski poziom baterii",
                        detail=(
                            f"Bateria {battery:.0f}%; "
                            f"próg {self._zigbee_low_battery_percent:.0f}%"
                        ),
                    )
                )

        return signals
