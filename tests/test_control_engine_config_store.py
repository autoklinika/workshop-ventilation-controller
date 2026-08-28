from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ventilation_core.calendar import default_calendar_config
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.shadow_policy import ShadowOutputTuning, ShadowPolicyV1
from ventilation_core.infrastructure.sqlite_calendar_store import SqliteCalendarStore
from ventilation_core.infrastructure.sqlite_control_engine_store import SqliteControlEngineStore


def tuned_config() -> ControlEngineConfig:
    tuning = ShadowOutputTuning(
        normal_air_request_pct=30.0,
        boost_air_request_pct=50.0,
        high_air_request_pct=75.0,
        max_air_request_pct=100.0,
        thermal_normal_limit_pct=100.0,
        thermal_limiting_limit_pct=60.0,
        thermal_minimum_limit_pct=30.0,
        thermal_protection_limit_pct=15.0,
        extract_bias_pct=5.0,
        aero_normal_speed=1,
        aero_boost_speed=2,
        aero_high_speed=3,
        aero_max_speed=3,
        pm2_5_hysteresis_ug_m3=2.0,
        voc_hysteresis_index=10.0,
        nox_hysteresis_index=5.0,
        temperature_hysteresis_celsius=0.5,
        pm2_5_boost_confirmation_seconds=60.0,
        state_minimum_hold_seconds=120.0,
        boost_decay_seconds=180.0,
        sensor_fallback_supply_pct=55.0,
        sensor_fallback_extract_pct=60.0,
        aero_sensor_fallback_speed=2,
        tacho_failure_confirmation_seconds=5.0,
        tacho_supply_fault_fallback_supply_pct=11.0,
        tacho_supply_fault_fallback_extract_pct=61.0,
        tacho_extract_fault_fallback_supply_pct=62.0,
        tacho_extract_fault_fallback_extract_pct=12.0,
        tacho_both_fault_fallback_supply_pct=33.0,
        tacho_both_fault_fallback_extract_pct=44.0,
    )
    return ControlEngineConfig(
        policy=ShadowPolicyV1(
            version="shadow-policy-v1-test",
            pm2_5_reference_ug_m3=15.0,
            pm2_5_high_ug_m3=25.0,
            pm2_5_max_ug_m3=50.0,
            pm10_reference_ug_m3=45.0,
            voc_boost_index=150.0,
            voc_high_index=200.0,
            voc_max_index=300.0,
            nox_boost_index=10.0,
            nox_high_index=50.0,
            nox_max_index=100.0,
            temperature_normal_above_celsius=20.0,
            temperature_limiting_from_celsius=18.0,
            temperature_minimum_from_celsius=16.0,
            tuning=tuning,
        )
    )


class ControlEngineConfigContractTest(unittest.TestCase):
    def test_default_config_roundtrip_keeps_all_none_tuning(self) -> None:
        config = ControlEngineConfig()
        payload = config.to_dict()
        restored = ControlEngineConfig.from_dict(payload)
        self.assertEqual(restored, config)
        self.assertFalse(restored.policy.tuning.outputs_configured)
        self.assertFalse(restored.policy.tuning.dynamics_configured)
        self.assertFalse(restored.policy.tuning.fan_sensor_fallback_configured)
        self.assertIsNone(restored.policy.tuning.tacho_failure_confirmation_seconds)
        self.assertFalse(restored.policy.tuning.tacho_supply_fault_fallback_configured)
        self.assertFalse(restored.policy.tuning.tacho_extract_fault_fallback_configured)
        self.assertFalse(restored.policy.tuning.tacho_both_fault_fallback_configured)
        self.assertNotIn("actuation_enabled", payload)

    def test_tuned_config_roundtrip_is_exact(self) -> None:
        config = tuned_config()
        restored = ControlEngineConfig.from_dict(config.to_dict())
        self.assertEqual(restored, config)
        self.assertEqual(restored.policy.tuning.tacho_failure_confirmation_seconds, 5.0)
        self.assertEqual(restored.policy.tuning.tacho_fault_fallback("SUPPLY"), (11.0, 61.0))
        self.assertEqual(restored.policy.tuning.tacho_fault_fallback("EXTRACT"), (62.0, 12.0))
        self.assertEqual(restored.policy.tuning.tacho_fault_fallback("BOTH"), (33.0, 44.0))

    def test_unknown_top_level_field_is_rejected(self) -> None:
        payload = ControlEngineConfig().to_dict()
        payload["actuation_enabled"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            ControlEngineConfig.from_dict(payload)

    def test_unknown_tuning_field_is_rejected(self) -> None:
        payload = ControlEngineConfig().to_dict()
        payload["policy"]["tuning"]["magic_pct"] = 42
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            ControlEngineConfig.from_dict(payload)

    def test_bool_and_text_are_not_coerced_to_numbers(self) -> None:
        payload = ControlEngineConfig().to_dict()
        payload["policy"]["pm2_5_high_ug_m3"] = "25"
        with self.assertRaisesRegex(ValueError, "without type coercion"):
            ControlEngineConfig.from_dict(payload)

        payload = ControlEngineConfig().to_dict()
        payload["policy"]["tuning"]["normal_air_request_pct"] = True
        with self.assertRaisesRegex(ValueError, "without type coercion"):
            ControlEngineConfig.from_dict(payload)

        payload = ControlEngineConfig().to_dict()
        payload["policy"]["tuning"]["tacho_failure_confirmation_seconds"] = True
        with self.assertRaisesRegex(ValueError, "without type coercion"):
            ControlEngineConfig.from_dict(payload)

        payload = ControlEngineConfig().to_dict()
        payload["policy"]["tuning"]["tacho_supply_fault_fallback_supply_pct"] = "11"
        with self.assertRaisesRegex(ValueError, "without type coercion"):
            ControlEngineConfig.from_dict(payload)

        payload = ControlEngineConfig().to_dict()
        payload["policy"]["tuning"]["aero_normal_speed"] = 1.0
        with self.assertRaisesRegex(ValueError, "integer"):
            ControlEngineConfig.from_dict(payload)

    def test_non_finite_numbers_are_rejected(self) -> None:
        payload = ControlEngineConfig().to_dict()
        payload["policy"]["voc_high_index"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            ControlEngineConfig.from_dict(payload)

    def test_negative_tacho_confirmation_is_rejected(self) -> None:
        payload = ControlEngineConfig().to_dict()
        payload["policy"]["tuning"]["tacho_failure_confirmation_seconds"] = -0.1
        with self.assertRaisesRegex(ValueError, "tacho_failure_confirmation_seconds must be non-negative"):
            ControlEngineConfig.from_dict(payload)

    def test_partial_tacho_fallback_pair_is_rejected_before_persistence(self) -> None:
        payload = ControlEngineConfig().to_dict()
        payload["policy"]["tuning"]["tacho_supply_fault_fallback_supply_pct"] = 11.0
        with self.assertRaisesRegex(ValueError, "TACHO supply fault fallback requires both"):
            ControlEngineConfig.from_dict(payload)

    def test_threshold_ordering_is_rejected_before_persistence(self) -> None:
        payload = ControlEngineConfig().to_dict()
        payload["policy"]["voc_boost_index"] = 250.0
        payload["policy"]["voc_high_index"] = 200.0
        with self.assertRaisesRegex(ValueError, "VOC thresholds"):
            ControlEngineConfig.from_dict(payload)

        payload = ControlEngineConfig().to_dict()
        payload["policy"]["temperature_normal_above_celsius"] = 15.0
        with self.assertRaisesRegex(ValueError, "Temperature thresholds"):
            ControlEngineConfig.from_dict(payload)


class SqliteControlEngineStoreTest(unittest.TestCase):
    def test_initial_config_and_revisioned_replace_survive_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.sqlite3"
            store = SqliteControlEngineStore(path, initial_config=ControlEngineConfig())
            config, revision = store.load()
            self.assertEqual(revision, 1)
            self.assertEqual(config, ControlEngineConfig())

            revision = store.replace(tuned_config())
            self.assertEqual(revision, 2)
            store.close()

            reopened = SqliteControlEngineStore(path)
            loaded, revision = reopened.load()
            self.assertEqual(revision, 2)
            self.assertEqual(loaded, tuned_config())
            self.assertEqual(loaded.policy.tuning.tacho_failure_confirmation_seconds, 5.0)
            self.assertEqual(loaded.policy.tuning.tacho_fault_fallback("SUPPLY"), (11.0, 61.0))
            self.assertEqual(loaded.policy.tuning.tacho_fault_fallback("EXTRACT"), (62.0, 12.0))
            self.assertEqual(loaded.policy.tuning.tacho_fault_fallback("BOTH"), (33.0, 44.0))
            reopened.close()

    def test_control_engine_and_calendar_share_automation_db_without_collision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.sqlite3"
            calendar = SqliteCalendarStore(path, initial_config=default_calendar_config())
            control = SqliteControlEngineStore(path, initial_config=tuned_config())

            calendar_config, calendar_revision = calendar.load()
            control_config, control_revision = control.load()
            self.assertEqual(calendar_revision, 1)
            self.assertEqual(control_revision, 1)
            self.assertEqual(calendar_config, default_calendar_config())
            self.assertEqual(control_config, tuned_config())

            with sqlite3.connect(path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            self.assertIn("calendar_configuration", tables)
            self.assertIn("control_engine_configuration", tables)

            control.close()
            calendar.close()

    def test_missing_uninitialized_row_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteControlEngineStore(Path(directory) / "automation.sqlite3")
            with self.assertRaisesRegex(RuntimeError, "not initialized"):
                store.load()
            store.close()


if __name__ == "__main__":
    unittest.main()
