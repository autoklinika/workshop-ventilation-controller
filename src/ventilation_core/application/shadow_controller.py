from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Protocol

from ventilation_core.domain.models import AlarmSeverity, CoreState
from ventilation_core.domain.shadow import (
    ShadowAutomationState,
    ShadowAutomationStatus,
    ShadowZoneProposal,
)
from ventilation_core.domain.shadow_dynamics import (
    AirQualityDynamicsTracker,
    ThermalDynamicsTracker,
)
from ventilation_core.domain.shadow_policy import AirQualityLevel, ShadowPolicyV1, ThermalBand


@dataclass(frozen=True)
class ShadowZoneBinding:
    zone: str
    sensor_address: int
    actuator_kind: str


DEFAULT_SHADOW_ZONE_BINDINGS: tuple[ShadowZoneBinding, ...] = (
    ShadowZoneBinding("zone-1", 1, "fans"),
    ShadowZoneBinding("zone-2", 2, "aero"),
)


class ShadowAutomationEvaluator(Protocol):
    def evaluate(self, state: CoreState) -> ShadowAutomationState: ...


def _validate_bindings(bindings: tuple[ShadowZoneBinding, ...]) -> None:
    if not bindings:
        raise ValueError("At least one SHADOW zone mapping is required")
    zones: set[str] = set()
    addresses: set[int] = set()
    for binding in bindings:
        if not binding.zone or binding.zone.strip() != binding.zone:
            raise ValueError("SHADOW zone identifiers must be non-empty text")
        if binding.zone in zones:
            raise ValueError(f"Duplicate SHADOW zone: {binding.zone}")
        if (
            isinstance(binding.sensor_address, bool)
            or not isinstance(binding.sensor_address, int)
            or not 1 <= binding.sensor_address <= 247
        ):
            raise ValueError("SHADOW sensor addresses must be Modbus addresses 1..247")
        if binding.sensor_address in addresses:
            raise ValueError(f"Duplicate SHADOW sensor address: {binding.sensor_address}")
        if binding.actuator_kind not in {"fans", "aero"}:
            raise ValueError(f"Unsupported SHADOW actuator kind: {binding.actuator_kind}")
        zones.add(binding.zone)
        addresses.add(binding.sensor_address)


class UnconfiguredShadowAutomationEvaluator:
    """Legacy-safe fallback that publishes context but no policy classification."""

    def __init__(
        self,
        *,
        zone_bindings: tuple[ShadowZoneBinding, ...] = DEFAULT_SHADOW_ZONE_BINDINGS,
    ) -> None:
        _validate_bindings(zone_bindings)
        self._zone_bindings = tuple(zone_bindings)

    def evaluate(self, state: CoreState) -> ShadowAutomationState:
        now = datetime.now(timezone.utc).isoformat()
        safety_blocked = _safety_blocked(state)
        calendar_phase, calendar_mode, calendar_profile = _calendar_context(state)
        sensor_by_address = _sensor_by_address(state)

        proposals: list[ShadowZoneProposal] = []
        for binding in self._zone_bindings:
            node = sensor_by_address.get(binding.sensor_address)
            sensor_usable = _sensor_usable(node)
            if safety_blocked:
                reason = "SAFETY_BLOCK_ACTIVE"
            elif calendar_phase == "UNKNOWN":
                reason = "CALENDAR_CONTEXT_UNKNOWN"
            elif not sensor_usable:
                reason = "SENSOR_CONTEXT_UNAVAILABLE"
            else:
                reason = "POLICY_NOT_CONFIGURED"
            proposals.append(
                ShadowZoneProposal(
                    zone=binding.zone,
                    calendar_phase=calendar_phase,
                    calendar_mode=calendar_mode,
                    calendar_profile=calendar_profile,
                    sensor_address=binding.sensor_address,
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


class PolicyShadowAutomationEvaluator:
    """Stateful, deterministic Control Engine V1 running strictly in SHADOW mode.

    The evaluator owns hysteresis/debounce state per logical zone, but it has no
    actuator port and therefore cannot change DAC or AERO outputs. Until site
    tuning is explicitly configured it retains the previous transparent SHADOW
    classification behaviour.
    """

    def __init__(
        self,
        policy: ShadowPolicyV1 | None = None,
        *,
        zone_bindings: tuple[ShadowZoneBinding, ...] = DEFAULT_SHADOW_ZONE_BINDINGS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        _validate_bindings(zone_bindings)
        self._policy = policy or ShadowPolicyV1()
        self._zone_bindings = tuple(zone_bindings)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._air_dynamics = {
            binding.zone: AirQualityDynamicsTracker() for binding in self._zone_bindings
        }
        self._thermal_dynamics = {
            binding.zone: ThermalDynamicsTracker()
            for binding in self._zone_bindings
            if binding.actuator_kind == "fans"
        }

    @property
    def policy(self) -> ShadowPolicyV1:
        return self._policy

    def evaluate(self, state: CoreState) -> ShadowAutomationState:
        with self._lock:
            return self._evaluate_locked(state)

    def _evaluate_locked(self, state: CoreState) -> ShadowAutomationState:
        now_dt = self._clock()
        if now_dt.tzinfo is None or now_dt.utcoffset() is None:
            raise ValueError("SHADOW Control Engine clock must be timezone-aware")
        now_dt = now_dt.astimezone(timezone.utc)
        now = now_dt.isoformat()
        safety_blocked = _safety_blocked(state)
        calendar_phase, calendar_mode, calendar_profile = _calendar_context(state)
        sensor_by_address = _sensor_by_address(state)
        degraded = False
        proposals: list[ShadowZoneProposal] = []

        for binding in self._zone_bindings:
            node = sensor_by_address.get(binding.sensor_address)
            sensor_usable = _sensor_usable(node)

            pm2_5 = None
            pm10 = None
            voc = None
            nox = None
            inside_temperature = None
            if node is not None:
                pm2_5 = node.reading.pm2_5_ug_m3
                pm10 = node.reading.pm10_0_ug_m3
                voc = node.reading.voc_index
                nox = node.reading.nox_index
                inside_temperature = node.reading.temperature_celsius

            pm2_5_level = self._policy.classify_pm2_5(pm2_5)
            voc_level = self._policy.classify_voc(voc)
            nox_level = self._policy.classify_nox(nox)

            dynamics = self._air_dynamics[binding.zone].update(
                self._policy,
                pm2_5_ug_m3=pm2_5,
                voc_index=voc,
                nox_index=nox,
                now_utc=now_dt,
            )
            raw_air_level = dynamics.raw_level
            raw_air_driver = dynamics.raw_driver
            air_level = dynamics.effective_level
            air_driver = dynamics.effective_driver

            if binding.actuator_kind == "fans":
                raw_thermal_band, thermal_band = self._thermal_dynamics[binding.zone].update(
                    self._policy,
                    temperature_celsius=inside_temperature,
                )
            else:
                raw_thermal_band = ThermalBand.NOT_APPLICABLE
                thermal_band = ThermalBand.NOT_APPLICABLE

            air_request_pct = self._policy.air_request_pct(air_level)
            temperature_limit_pct = (
                self._policy.temperature_limit_pct(thermal_band)
                if binding.actuator_kind == "fans"
                else None
            )

            air_quality_override = bool(
                binding.actuator_kind == "fans"
                and air_level is not None
                and air_level > AirQualityLevel.NORMAL
                and thermal_band
                in {
                    ThermalBand.LIMITING,
                    ThermalBand.MINIMUM,
                    ThermalBand.PROTECTION,
                }
            )

            final_supply_pct = None
            final_extract_pct = None
            proposed_aero_speed = None
            if self._policy.tuning.outputs_configured and not safety_blocked and sensor_usable:
                if binding.actuator_kind == "fans" and air_request_pct is not None:
                    if (
                        air_level == AirQualityLevel.NORMAL
                        and temperature_limit_pct is not None
                    ):
                        final_supply_pct = min(air_request_pct, temperature_limit_pct)
                    else:
                        # AIR QUALITY outranks temperature/energy when air is degraded.
                        final_supply_pct = air_request_pct
                    final_extract_pct = min(
                        100.0,
                        final_supply_pct
                        + float(self._policy.tuning.extract_bias_pct or 0.0),
                    )
                elif binding.actuator_kind == "aero":
                    proposed_aero_speed = self._policy.aero_speed(air_level)

            automation_state = self._automation_state(
                binding=binding,
                safety_blocked=safety_blocked,
                calendar_phase=calendar_phase,
                calendar_mode=calendar_mode,
                sensor_usable=sensor_usable,
                air_level=air_level,
                thermal_band=thermal_band,
            )
            reason = self._control_reason(
                binding=binding,
                safety_blocked=safety_blocked,
                calendar_phase=calendar_phase,
                sensor_usable=sensor_usable,
                air_level=air_level,
                air_driver=air_driver,
                thermal_band=thermal_band,
                air_quality_override=air_quality_override,
                dynamics_pending_level=dynamics.pending_level,
                dynamics_transition_reason=dynamics.transition_reason,
            )

            if (
                calendar_phase == "UNKNOWN"
                or not sensor_usable
                or air_level is None
                or (
                    binding.actuator_kind == "fans"
                    and thermal_band == ThermalBand.UNKNOWN
                )
            ):
                degraded = True

            proposals.append(
                ShadowZoneProposal(
                    zone=binding.zone,
                    calendar_phase=calendar_phase,
                    calendar_mode=calendar_mode,
                    calendar_profile=calendar_profile,
                    sensor_address=binding.sensor_address,
                    sensor_usable=sensor_usable,
                    automation_state=automation_state,
                    raw_air_quality_level=(
                        None if raw_air_level is None else raw_air_level.name
                    ),
                    raw_air_quality_driver=raw_air_driver,
                    air_quality_level=None if air_level is None else air_level.name,
                    air_quality_driver=air_driver,
                    pm2_5_level=None if pm2_5_level is None else pm2_5_level.name,
                    voc_level=None if voc_level is None else voc_level.name,
                    nox_level=None if nox_level is None else nox_level.name,
                    pm10_reference_exceeded=self._policy.pm10_reference_exceeded(pm10),
                    air_quality_effective_since_utc=dynamics.effective_since_utc,
                    dynamics_pending_level=(
                        None if dynamics.pending_level is None else dynamics.pending_level.name
                    ),
                    dynamics_pending_driver=dynamics.pending_driver,
                    dynamics_pending_since_utc=dynamics.pending_since_utc,
                    dynamics_transition_reason=dynamics.transition_reason,
                    inside_temperature_celsius=inside_temperature,
                    # Outdoor/supply-air temperature is intentionally unavailable
                    # until the selected Zigbee measurement path is integrated.
                    outside_temperature_celsius=None,
                    raw_thermal_band=raw_thermal_band.value,
                    thermal_band=thermal_band.value,
                    air_request_pct=air_request_pct,
                    temperature_limit_pct=temperature_limit_pct,
                    final_supply_pct=final_supply_pct,
                    final_extract_pct=final_extract_pct,
                    safety_override=safety_blocked,
                    air_quality_override=air_quality_override,
                    proposed_supply_voltage=None,
                    proposed_extract_voltage=None,
                    proposed_aero_speed=proposed_aero_speed,
                    control_reason=reason,
                )
            )

        if safety_blocked:
            status = ShadowAutomationStatus.BLOCKED_SAFETY
        elif degraded:
            status = ShadowAutomationStatus.DEGRADED
        elif not self._policy.tuning.complete:
            status = ShadowAutomationStatus.TUNING_REQUIRED
        else:
            status = ShadowAutomationStatus.READY

        return ShadowAutomationState(
            enabled=True,
            actuation_supported=False,
            status=status,
            evaluated_at_utc=now,
            policy_version=self._policy.version,
            tuning_complete=self._policy.tuning.complete,
            zones=tuple(proposals),
        )

    def _automation_state(
        self,
        *,
        binding: ShadowZoneBinding,
        safety_blocked: bool,
        calendar_phase: str,
        calendar_mode: str | None,
        sensor_usable: bool,
        air_level: AirQualityLevel | None,
        thermal_band: ThermalBand,
    ) -> str:
        if safety_blocked or calendar_phase == "UNKNOWN" or not sensor_usable:
            return "FAULT"
        if air_level is None:
            return "FAULT"
        if binding.actuator_kind == "fans" and thermal_band == ThermalBand.UNKNOWN:
            return "FAULT"
        if air_level == AirQualityLevel.MAX:
            return "EMERGENCY_VENT"
        if air_level >= AirQualityLevel.BOOST:
            return "BOOST"
        if calendar_phase == "PREVENTILATION":
            return "PREVENTILATION"
        if calendar_phase == "PURGE":
            return "PURGE"
        if calendar_phase == "ACTIVE":
            if binding.actuator_kind == "fans" and thermal_band in {
                ThermalBand.LIMITING,
                ThermalBand.MINIMUM,
                ThermalBand.PROTECTION,
            }:
                return "TEMP_LIMIT"
            return "NORMAL"
        if calendar_mode == "OFF":
            return "OFF"
        return "STANDBY"

    def _control_reason(
        self,
        *,
        binding: ShadowZoneBinding,
        safety_blocked: bool,
        calendar_phase: str,
        sensor_usable: bool,
        air_level: AirQualityLevel | None,
        air_driver: str | None,
        thermal_band: ThermalBand,
        air_quality_override: bool,
        dynamics_pending_level: AirQualityLevel | None,
        dynamics_transition_reason: str,
    ) -> str:
        if safety_blocked:
            return "SAFETY_BLOCK_ACTIVE"
        if calendar_phase == "UNKNOWN":
            return "CALENDAR_CONTEXT_UNKNOWN"
        if not sensor_usable:
            return "SENSOR_CONTEXT_UNAVAILABLE"
        if air_level is None:
            return "AIR_QUALITY_INPUTS_UNAVAILABLE"
        if binding.actuator_kind == "fans" and thermal_band == ThermalBand.UNKNOWN:
            return "TEMPERATURE_CONTEXT_UNAVAILABLE"
        if (
            dynamics_pending_level is not None
            and dynamics_transition_reason == "ESCALATION_CONFIRMING"
        ):
            return f"AIR_QUALITY_CONFIRMING:{dynamics_pending_level.name}"
        if air_quality_override:
            return "LOW_TEMPERATURE + AIR_QUALITY_OVERRIDE"
        if air_level == AirQualityLevel.MAX:
            return f"AIR_QUALITY_MAX:{air_driver}"
        if air_level == AirQualityLevel.HIGH:
            return f"AIR_QUALITY_HIGH:{air_driver}"
        if air_level == AirQualityLevel.BOOST:
            if (
                air_driver == "PM2_5"
                and self._policy.tuning.pm2_5_boost_confirmation_seconds is None
            ):
                return "PM2_5_BOOST_CONFIRMATION_TUNING_REQUIRED"
            return f"AIR_QUALITY_BOOST:{air_driver}"
        if thermal_band == ThermalBand.PROTECTION:
            return "THERMAL_PROTECTION"
        if thermal_band == ThermalBand.MINIMUM:
            return "THERMAL_MINIMUM"
        if thermal_band == ThermalBand.LIMITING:
            return "THERMAL_LIMITING"
        return "AIR_QUALITY_NORMAL"


def _safety_blocked(state: CoreState) -> bool:
    return (
        state.hardware_ready is not True
        or state.output_state_known is not True
        or any(alarm.severity == AlarmSeverity.CRITICAL for alarm in state.active_alarms)
    )


def _calendar_context(state: CoreState) -> tuple[str, str | None, str | None]:
    calendar = state.calendar
    if calendar is None or calendar.available is not True:
        return "UNKNOWN", None, None
    mode = None if calendar.effective_mode is None else calendar.effective_mode.value
    return calendar.phase.value, mode, calendar.effective_profile


def _sensor_by_address(state: CoreState) -> dict[int, object]:
    if state.sensor_bus is None:
        return {}
    return {node.slave_address: node for node in state.sensor_bus.nodes}


def _sensor_usable(node: object | None) -> bool:
    return bool(
        node is not None
        and getattr(node, "online") is True
        and getattr(node, "usable") is True
        and getattr(node, "measurement_valid") is True
        and getattr(node, "measurement_stale") is not True
    )
