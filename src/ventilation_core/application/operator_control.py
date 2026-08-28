from __future__ import annotations

from dataclasses import replace

from ventilation_core.domain.operator_control import OperatorControlIntent, OperatorMode
from ventilation_core.domain.shadow import (
    ShadowAutomationState,
    ShadowAutomationStatus,
    ShadowZoneProposal,
)
from ventilation_core.domain.shadow_policy import AirQualityLevel, ShadowPolicyV1


def _level(zone: ShadowZoneProposal) -> AirQualityLevel | None:
    if zone.air_quality_level is None:
        return None
    try:
        return AirQualityLevel[zone.air_quality_level]
    except KeyError as exc:
        raise RuntimeError(
            f"Unsupported air-quality level in SHADOW proposal: {zone.air_quality_level}"
        ) from exc


def _operator_fields(
    zone: ShadowZoneProposal,
    intent: OperatorControlIntent,
    *,
    overridden: bool = False,
    override_reason: str | None = None,
) -> ShadowZoneProposal:
    return replace(
        zone,
        operator_mode=intent.mode.value,
        operator_manual_supply_pct=intent.manual_supply_pct,
        operator_manual_extract_pct=intent.manual_extract_pct,
        operator_manual_aero_speed=intent.manual_aero_speed,
        operator_override=overridden,
        operator_override_reason=override_reason,
    )


def _manual_fans(
    zone: ShadowZoneProposal,
    policy: ShadowPolicyV1,
    intent: OperatorControlIntent,
) -> ShadowZoneProposal:
    assert intent.manual_supply_pct is not None
    assert intent.manual_extract_pct is not None

    if zone.safety_override:
        return _operator_fields(
            replace(
                zone,
                automation_state="FAULT",
                final_supply_pct=None,
                final_extract_pct=None,
                proposed_supply_voltage=None,
                proposed_extract_voltage=None,
                control_reason="OPERATOR_MANUAL:SAFETY_BLOCK_ACTIVE",
            ),
            intent,
            overridden=True,
            override_reason="SAFETY_BLOCK_ACTIVE",
        )

    if not zone.sensor_usable:
        if policy.tuning.fan_sensor_fallback_configured:
            fallback_supply = float(policy.tuning.sensor_fallback_supply_pct or 0.0)
            fallback_extract = float(policy.tuning.sensor_fallback_extract_pct or 0.0)
            final_supply = max(float(intent.manual_supply_pct), fallback_supply)
            final_extract = max(float(intent.manual_extract_pct), fallback_extract)
            return _operator_fields(
                replace(
                    zone,
                    automation_state="FAULT",
                    final_supply_pct=final_supply,
                    final_extract_pct=final_extract,
                    sensor_fallback_applied=True,
                    air_quality_override=False,
                    proposed_supply_voltage=None,
                    proposed_extract_voltage=None,
                    control_reason="OPERATOR_MANUAL:SENSOR_CONTEXT_UNAVAILABLE:FALLBACK",
                ),
                intent,
                overridden=True,
                override_reason="SENSOR_FALLBACK",
            )
        return _operator_fields(
            replace(
                zone,
                automation_state="FAULT",
                final_supply_pct=None,
                final_extract_pct=None,
                sensor_fallback_applied=False,
                air_quality_override=False,
                proposed_supply_voltage=None,
                proposed_extract_voltage=None,
                control_reason=(
                    "OPERATOR_MANUAL:SENSOR_CONTEXT_UNAVAILABLE:"
                    "FALLBACK_TUNING_REQUIRED"
                ),
            ),
            intent,
            overridden=True,
            override_reason="SENSOR_CONTEXT_UNAVAILABLE",
        )

    level = _level(zone)
    if level is None or zone.air_request_pct is None or not policy.tuning.fan_outputs_configured:
        return _operator_fields(
            replace(
                zone,
                automation_state="FAULT",
                final_supply_pct=None,
                final_extract_pct=None,
                air_quality_override=False,
                proposed_supply_voltage=None,
                proposed_extract_voltage=None,
                control_reason="OPERATOR_MANUAL:AIR_QUALITY_OVERRIDE_TUNING_REQUIRED",
            ),
            intent,
            overridden=True,
            override_reason="AIR_QUALITY_OVERRIDE_TUNING_REQUIRED",
        )

    manual_supply = float(intent.manual_supply_pct)
    manual_extract = float(intent.manual_extract_pct)
    if level == AirQualityLevel.NORMAL:
        return _operator_fields(
            replace(
                zone,
                automation_state="MANUAL",
                final_supply_pct=manual_supply,
                final_extract_pct=manual_extract,
                air_quality_override=False,
                proposed_supply_voltage=None,
                proposed_extract_voltage=None,
                control_reason="OPERATOR_MANUAL",
            ),
            intent,
        )

    bias = float(policy.tuning.extract_bias_pct or 0.0)
    safety_supply = float(zone.air_request_pct)
    safety_extract = min(100.0, safety_supply + bias)
    final_supply = max(manual_supply, safety_supply)
    final_extract = max(manual_extract, safety_extract)
    state = "EMERGENCY_VENT" if level == AirQualityLevel.MAX else "BOOST"
    driver = zone.air_quality_driver or "UNKNOWN"
    return _operator_fields(
        replace(
            zone,
            automation_state=state,
            final_supply_pct=final_supply,
            final_extract_pct=final_extract,
            air_quality_override=False,
            proposed_supply_voltage=None,
            proposed_extract_voltage=None,
            control_reason=f"OPERATOR_MANUAL:AIR_QUALITY_{level.name}:{driver}",
        ),
        intent,
        overridden=True,
        override_reason=f"AIR_QUALITY_{level.name}",
    )


def _manual_aero(
    zone: ShadowZoneProposal,
    policy: ShadowPolicyV1,
    intent: OperatorControlIntent,
) -> ShadowZoneProposal:
    assert intent.manual_aero_speed is not None

    if zone.safety_override:
        return _operator_fields(
            replace(
                zone,
                automation_state="FAULT",
                proposed_aero_speed=None,
                control_reason="OPERATOR_MANUAL:SAFETY_BLOCK_ACTIVE",
            ),
            intent,
            overridden=True,
            override_reason="SAFETY_BLOCK_ACTIVE",
        )

    if not zone.sensor_usable:
        if policy.tuning.aero_sensor_fallback_configured:
            fallback = int(policy.tuning.aero_sensor_fallback_speed or 0)
            final_speed = max(int(intent.manual_aero_speed), fallback)
            return _operator_fields(
                replace(
                    zone,
                    automation_state="FAULT",
                    proposed_aero_speed=final_speed,
                    sensor_fallback_applied=True,
                    control_reason="OPERATOR_MANUAL:SENSOR_CONTEXT_UNAVAILABLE:FALLBACK",
                ),
                intent,
                overridden=True,
                override_reason="SENSOR_FALLBACK",
            )
        return _operator_fields(
            replace(
                zone,
                automation_state="FAULT",
                proposed_aero_speed=None,
                sensor_fallback_applied=False,
                control_reason=(
                    "OPERATOR_MANUAL:SENSOR_CONTEXT_UNAVAILABLE:"
                    "FALLBACK_TUNING_REQUIRED"
                ),
            ),
            intent,
            overridden=True,
            override_reason="SENSOR_CONTEXT_UNAVAILABLE",
        )

    level = _level(zone)
    if level is None or not policy.tuning.aero_outputs_configured:
        return _operator_fields(
            replace(
                zone,
                automation_state="FAULT",
                proposed_aero_speed=None,
                control_reason="OPERATOR_MANUAL:AIR_QUALITY_OVERRIDE_TUNING_REQUIRED",
            ),
            intent,
            overridden=True,
            override_reason="AIR_QUALITY_OVERRIDE_TUNING_REQUIRED",
        )

    automatic_speed = policy.aero_speed(level)
    if automatic_speed is None:
        return _operator_fields(
            replace(
                zone,
                automation_state="FAULT",
                proposed_aero_speed=None,
                control_reason="OPERATOR_MANUAL:AIR_QUALITY_OVERRIDE_TUNING_REQUIRED",
            ),
            intent,
            overridden=True,
            override_reason="AIR_QUALITY_OVERRIDE_TUNING_REQUIRED",
        )

    manual_speed = int(intent.manual_aero_speed)
    if level == AirQualityLevel.NORMAL:
        return _operator_fields(
            replace(
                zone,
                automation_state="MANUAL",
                proposed_aero_speed=manual_speed,
                control_reason="OPERATOR_MANUAL",
            ),
            intent,
        )

    final_speed = max(manual_speed, int(automatic_speed))
    state = "EMERGENCY_VENT" if level == AirQualityLevel.MAX else "BOOST"
    driver = zone.air_quality_driver or "UNKNOWN"
    return _operator_fields(
        replace(
            zone,
            automation_state=state,
            proposed_aero_speed=final_speed,
            control_reason=f"OPERATOR_MANUAL:AIR_QUALITY_{level.name}:{driver}",
        ),
        intent,
        overridden=True,
        override_reason=f"AIR_QUALITY_{level.name}",
    )


def apply_operator_intent(
    base: ShadowAutomationState,
    policy: ShadowPolicyV1,
    intent: OperatorControlIntent,
    *,
    revision: int | None = None,
) -> ShadowAutomationState:
    """Apply the operator layer without creating any physical-control authority."""

    if base.actuation_supported is not False:
        raise RuntimeError("operator layer received an actuating Control Engine state")

    if intent.mode == OperatorMode.AUTO:
        zones = tuple(_operator_fields(zone, intent) for zone in base.zones)
        return replace(
            base,
            zones=zones,
            operator_mode=intent.mode.value,
            operator_manual_supply_pct=None,
            operator_manual_extract_pct=None,
            operator_manual_aero_speed=None,
            operator_intent_revision=revision,
            operator_intent_persistent=False,
        )

    zones: list[ShadowZoneProposal] = []
    for zone in base.zones:
        if zone.proposed_supply_voltage is not None or zone.proposed_extract_voltage is not None:
            raise RuntimeError("operator layer received a physical voltage proposal")
        if zone.zone == "zone-1":
            zones.append(_manual_fans(zone, policy, intent))
        elif zone.zone == "zone-2":
            zones.append(_manual_aero(zone, policy, intent))
        else:
            zones.append(
                _operator_fields(
                    replace(
                        zone,
                        automation_state="FAULT",
                        final_supply_pct=None,
                        final_extract_pct=None,
                        proposed_aero_speed=None,
                        control_reason="OPERATOR_MANUAL:UNSUPPORTED_ZONE",
                    ),
                    intent,
                    overridden=True,
                    override_reason="UNSUPPORTED_ZONE",
                )
            )

    if base.status == ShadowAutomationStatus.BLOCKED_SAFETY:
        status = ShadowAutomationStatus.BLOCKED_SAFETY
    elif any(zone.automation_state == "FAULT" for zone in zones):
        status = ShadowAutomationStatus.DEGRADED
    elif not base.tuning_complete:
        status = ShadowAutomationStatus.TUNING_REQUIRED
    else:
        status = ShadowAutomationStatus.READY

    return replace(
        base,
        status=status,
        zones=tuple(zones),
        operator_mode=intent.mode.value,
        operator_manual_supply_pct=intent.manual_supply_pct,
        operator_manual_extract_pct=intent.manual_extract_pct,
        operator_manual_aero_speed=intent.manual_aero_speed,
        operator_intent_revision=revision,
        operator_intent_persistent=False,
    )
