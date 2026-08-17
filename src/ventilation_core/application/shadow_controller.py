from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from ventilation_core.domain.models import AlarmSeverity, CoreState
from ventilation_core.domain.shadow import (
    ShadowAutomationState,
    ShadowAutomationStatus,
    ShadowZoneProposal,
)


DEFAULT_SHADOW_ZONE_SENSORS: tuple[tuple[str, int], ...] = (
    ("zone-1", 1),
    ("zone-2", 2),
)


class ShadowAutomationEvaluator(Protocol):
    def evaluate(self, state: CoreState) -> ShadowAutomationState: ...


class UnconfiguredShadowAutomationEvaluator:
    """Publish SHADOW inputs safely before deterministic policy thresholds exist.

    This evaluator is deliberately non-actuating. It exposes schedule/sensor context
    and a safety block, but never invents fan/AERO proposals while the policy is not
    configured and versioned.
    """

    def __init__(
        self,
        *,
        zone_sensors: tuple[tuple[str, int], ...] = DEFAULT_SHADOW_ZONE_SENSORS,
    ) -> None:
        if not zone_sensors:
            raise ValueError("At least one SHADOW zone mapping is required")
        zones: set[str] = set()
        addresses: set[int] = set()
        for zone, address in zone_sensors:
            if not isinstance(zone, str) or not zone or zone.strip() != zone:
                raise ValueError("SHADOW zone identifiers must be non-empty text")
            if zone in zones:
                raise ValueError(f"Duplicate SHADOW zone: {zone}")
            if isinstance(address, bool) or not isinstance(address, int) or not 1 <= address <= 247:
                raise ValueError("SHADOW sensor addresses must be Modbus addresses 1..247")
            if address in addresses:
                raise ValueError(f"Duplicate SHADOW sensor address: {address}")
            zones.add(zone)
            addresses.add(address)
        self._zone_sensors = tuple(zone_sensors)

    def evaluate(self, state: CoreState) -> ShadowAutomationState:
        now = datetime.now(timezone.utc).isoformat()
        safety_blocked = (
            state.hardware_ready is not True
            or state.output_state_known is not True
            or any(alarm.severity == AlarmSeverity.CRITICAL for alarm in state.active_alarms)
        )

        schedule_by_zone: dict[str, str] = {}
        if state.schedule is not None:
            schedule_by_zone = {
                zone.zone: zone.expectation.value
                for zone in state.schedule.zones
            }

        sensor_by_address = {}
        if state.sensor_bus is not None:
            sensor_by_address = {
                node.slave_address: node
                for node in state.sensor_bus.nodes
            }

        proposals: list[ShadowZoneProposal] = []
        for zone, sensor_address in self._zone_sensors:
            node = sensor_by_address.get(sensor_address)
            sensor_usable = bool(
                node is not None
                and node.online is True
                and node.usable is True
                and node.measurement_valid is True
                and node.measurement_stale is not True
            )
            expectation = schedule_by_zone.get(zone, "UNKNOWN")
            if safety_blocked:
                reason = "SAFETY_BLOCK_ACTIVE"
            elif expectation == "UNKNOWN":
                reason = "SCHEDULE_CONTEXT_UNKNOWN"
            elif not sensor_usable:
                reason = "SENSOR_CONTEXT_UNAVAILABLE"
            else:
                reason = "POLICY_NOT_CONFIGURED"
            proposals.append(
                ShadowZoneProposal(
                    zone=zone,
                    schedule_expectation=expectation,
                    sensor_address=sensor_address,
                    sensor_usable=sensor_usable,
                    safety_override=safety_blocked,
                    control_reason=reason,
                )
            )

        status = (
            ShadowAutomationStatus.BLOCKED_SAFETY
            if safety_blocked
            else ShadowAutomationStatus.POLICY_UNCONFIGURED
        )
        return ShadowAutomationState(
            enabled=True,
            actuation_supported=False,
            status=status,
            evaluated_at_utc=now,
            policy_version=None,
            zones=tuple(proposals),
        )
