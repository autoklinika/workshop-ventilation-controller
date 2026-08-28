from __future__ import annotations

import unittest

from ventilation_core.application.operator_control import apply_operator_intent
from ventilation_core.domain.operator_control import OperatorControlIntent, OperatorMode
from ventilation_core.domain.shadow import (
    ShadowAutomationState,
    ShadowAutomationStatus,
    ShadowZoneProposal,
)
from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1


def policy() -> ShadowPolicyV1:
    return ShadowPolicyV1(
        version="operator-test-v1",
        tuning=ShadowOutputTuning(
            normal_air_request_pct=20.0,
            boost_air_request_pct=40.0,
            high_air_request_pct=70.0,
            max_air_request_pct=100.0,
            thermal_normal_limit_pct=100.0,
            thermal_limiting_limit_pct=60.0,
            thermal_minimum_limit_pct=30.0,
            thermal_protection_limit_pct=10.0,
            extract_bias_pct=5.0,
            aero_normal_speed=0,
            aero_boost_speed=1,
            aero_high_speed=2,
            aero_max_speed=3,
            pm2_5_hysteresis_ug_m3=2.0,
            voc_hysteresis_index=10.0,
            nox_hysteresis_index=5.0,
            temperature_hysteresis_celsius=1.0,
            pm2_5_boost_confirmation_seconds=30.0,
            state_minimum_hold_seconds=60.0,
            boost_decay_seconds=120.0,
            sensor_fallback_supply_pct=45.0,
            sensor_fallback_extract_pct=50.0,
            aero_sensor_fallback_speed=2,
        ),
    )


def zone(
    address: int,
    *,
    level: str = "NORMAL",
    request: float = 20.0,
    sensor_usable: bool = True,
    safety: bool = False,
) -> ShadowZoneProposal:
    is_fan = address == 1
    return ShadowZoneProposal(
        zone="zone-1" if is_fan else "zone-2",
        calendar_phase="INACTIVE",
        calendar_mode="OFF",
        calendar_profile="TEST",
        sensor_address=address,
        sensor_usable=sensor_usable,
        automation_state="OFF",
        schedule_supply_pct=0.0,
        schedule_extract_pct=0.0,
        schedule_request_source="TEST_OFF",
        air_quality_level=level,
        air_quality_driver="VOC",
        air_request_pct=request,
        raw_thermal_band="PROTECTION" if is_fan else "NOT_APPLICABLE",
        thermal_band="PROTECTION" if is_fan else "NOT_APPLICABLE",
        temperature_limit_pct=10.0 if is_fan else None,
        final_supply_pct=0.0 if is_fan else None,
        final_extract_pct=0.0 if is_fan else None,
        safety_override=safety,
        proposed_supply_voltage=None,
        proposed_extract_voltage=None,
        proposed_aero_speed=0 if not is_fan else None,
        control_reason="BASE",
    )


def state(*, fan: ShadowZoneProposal | None = None, aero: ShadowZoneProposal | None = None, blocked: bool = False) -> ShadowAutomationState:
    return ShadowAutomationState(
        enabled=True,
        actuation_supported=False,
        status=(
            ShadowAutomationStatus.BLOCKED_SAFETY
            if blocked
            else ShadowAutomationStatus.READY
        ),
        evaluated_at_utc="2026-08-28T10:00:00+00:00",
        policy_version="operator-test-v1",
        zones=(fan or zone(1), aero or zone(2)),
        tuning_complete=True,
    )


class OperatorControlIntentContractTest(unittest.TestCase):
    def test_auto_is_default_and_must_not_carry_manual_values(self) -> None:
        intent = OperatorControlIntent()
        self.assertEqual(intent.mode, OperatorMode.AUTO)
        self.assertEqual(
            intent.to_dict(),
            {
                "mode": "AUTO",
                "manual_supply_pct": None,
                "manual_extract_pct": None,
                "manual_aero_speed": None,
            },
        )
        with self.assertRaises(ValueError):
            OperatorControlIntent.from_dict({"mode": "AUTO", "manual_supply_pct": 20})

    def test_manual_requires_all_strict_values(self) -> None:
        intent = OperatorControlIntent.from_dict(
            {
                "mode": "MANUAL",
                "manual_supply_pct": 20,
                "manual_extract_pct": 25.0,
                "manual_aero_speed": 1,
            }
        )
        self.assertEqual(intent.mode, OperatorMode.MANUAL)
        self.assertEqual(intent.manual_supply_pct, 20.0)
        self.assertEqual(intent.manual_extract_pct, 25.0)
        self.assertEqual(intent.manual_aero_speed, 1)

        invalid = (
            {"mode": "manual", "manual_supply_pct": 20, "manual_extract_pct": 25, "manual_aero_speed": 1},
            {"mode": "MANUAL", "manual_supply_pct": True, "manual_extract_pct": 25, "manual_aero_speed": 1},
            {"mode": "MANUAL", "manual_supply_pct": 20, "manual_extract_pct": 25, "manual_aero_speed": 4},
            {"mode": "MANUAL", "manual_supply_pct": 20, "manual_extract_pct": 25},
            {"mode": "MANUAL", "manual_supply_pct": 20, "manual_extract_pct": 25, "manual_aero_speed": 1, "actuate": True},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    OperatorControlIntent.from_dict(payload)


class OperatorControlLayerTest(unittest.TestCase):
    def test_auto_preserves_existing_control_engine_decision(self) -> None:
        base = state()
        result = apply_operator_intent(base, policy(), OperatorControlIntent(), revision=0)
        self.assertEqual(result.operator_mode, "AUTO")
        self.assertEqual(result.operator_intent_revision, 0)
        self.assertFalse(result.operator_intent_persistent)
        self.assertEqual(result.zones[0].final_supply_pct, 0.0)
        self.assertEqual(result.zones[0].automation_state, "OFF")
        self.assertFalse(result.zones[0].operator_override)

    def test_manual_good_air_ignores_calendar_and_thermal_energy_limit(self) -> None:
        intent = OperatorControlIntent.from_dict(
            {
                "mode": "MANUAL",
                "manual_supply_pct": 20,
                "manual_extract_pct": 25,
                "manual_aero_speed": 1,
            }
        )
        result = apply_operator_intent(state(), policy(), intent, revision=1)
        fan, aero = result.zones
        self.assertEqual(result.status, ShadowAutomationStatus.READY)
        self.assertEqual(result.operator_mode, "MANUAL")
        self.assertEqual(fan.automation_state, "MANUAL")
        self.assertEqual(fan.final_supply_pct, 20.0)
        self.assertEqual(fan.final_extract_pct, 25.0)
        self.assertEqual(fan.temperature_limit_pct, 10.0)
        self.assertEqual(fan.control_reason, "OPERATOR_MANUAL")
        self.assertFalse(fan.operator_override)
        self.assertEqual(aero.automation_state, "MANUAL")
        self.assertEqual(aero.proposed_aero_speed, 1)
        self.assertFalse(aero.operator_override)

    def test_air_quality_max_overrides_manual_and_enters_emergency(self) -> None:
        intent = OperatorControlIntent.from_dict(
            {
                "mode": "MANUAL",
                "manual_supply_pct": 20,
                "manual_extract_pct": 20,
                "manual_aero_speed": 0,
            }
        )
        base = state(
            fan=zone(1, level="MAX", request=100.0),
            aero=zone(2, level="MAX", request=100.0),
        )
        result = apply_operator_intent(base, policy(), intent, revision=2)
        fan, aero = result.zones
        self.assertEqual(fan.automation_state, "EMERGENCY_VENT")
        self.assertEqual(fan.final_supply_pct, 100.0)
        self.assertEqual(fan.final_extract_pct, 100.0)
        self.assertTrue(fan.operator_override)
        self.assertEqual(fan.operator_override_reason, "AIR_QUALITY_MAX")
        self.assertEqual(aero.automation_state, "EMERGENCY_VENT")
        self.assertEqual(aero.proposed_aero_speed, 3)
        self.assertTrue(aero.operator_override)
        self.assertEqual(aero.operator_override_reason, "AIR_QUALITY_MAX")

    def test_sensor_loss_uses_fallback_floor_even_outside_calendar(self) -> None:
        intent = OperatorControlIntent.from_dict(
            {
                "mode": "MANUAL",
                "manual_supply_pct": 20,
                "manual_extract_pct": 25,
                "manual_aero_speed": 1,
            }
        )
        base = state(
            fan=zone(1, sensor_usable=False),
            aero=zone(2, sensor_usable=False),
        )
        result = apply_operator_intent(base, policy(), intent)
        fan, aero = result.zones
        self.assertEqual(result.status, ShadowAutomationStatus.DEGRADED)
        self.assertEqual(fan.automation_state, "FAULT")
        self.assertTrue(fan.sensor_fallback_applied)
        self.assertEqual(fan.final_supply_pct, 45.0)
        self.assertEqual(fan.final_extract_pct, 50.0)
        self.assertEqual(fan.operator_override_reason, "SENSOR_FALLBACK")
        self.assertEqual(aero.automation_state, "FAULT")
        self.assertTrue(aero.sensor_fallback_applied)
        self.assertEqual(aero.proposed_aero_speed, 2)

    def test_hardware_or_critical_safety_block_rejects_manual_request(self) -> None:
        intent = OperatorControlIntent.from_dict(
            {
                "mode": "MANUAL",
                "manual_supply_pct": 80,
                "manual_extract_pct": 90,
                "manual_aero_speed": 3,
            }
        )
        base = state(
            fan=zone(1, safety=True),
            aero=zone(2, safety=True),
            blocked=True,
        )
        result = apply_operator_intent(base, policy(), intent)
        self.assertEqual(result.status, ShadowAutomationStatus.BLOCKED_SAFETY)
        for item in result.zones:
            self.assertEqual(item.automation_state, "FAULT")
            self.assertTrue(item.operator_override)
            self.assertEqual(item.operator_override_reason, "SAFETY_BLOCK_ACTIVE")
            self.assertIsNone(item.final_supply_pct)
            self.assertIsNone(item.final_extract_pct)
            self.assertIsNone(item.proposed_aero_speed)
            self.assertIsNone(item.proposed_supply_voltage)
            self.assertIsNone(item.proposed_extract_voltage)


if __name__ == "__main__":
    unittest.main()
