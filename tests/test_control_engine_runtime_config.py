from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ventilation_core.application.control_engine_runtime import PersistentControlEngineEvaluator
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.infrastructure.sqlite_control_engine_store import SqliteControlEngineStore


class PersistentControlEngineEvaluatorTest(unittest.TestCase):
    def test_configuration_readback_and_hot_replace_are_revisioned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteControlEngineStore(
                Path(directory) / "automation.sqlite3",
                initial_config=ControlEngineConfig(),
            )
            runtime = PersistentControlEngineEvaluator(store)
            initial = runtime.configuration()
            self.assertEqual(initial["revision"], 1)
            self.assertFalse(initial["actuation_supported"])
            self.assertIsNone(
                initial["config"]["policy"]["tuning"]["normal_air_request_pct"]
            )

            payload = ControlEngineConfig().to_dict()
            tuning = payload["policy"]["tuning"]
            tuning.update(
                {
                    "normal_air_request_pct": 30.0,
                    "boost_air_request_pct": 50.0,
                    "high_air_request_pct": 75.0,
                    "max_air_request_pct": 100.0,
                    "thermal_normal_limit_pct": 100.0,
                    "thermal_limiting_limit_pct": 60.0,
                    "thermal_minimum_limit_pct": 30.0,
                    "thermal_protection_limit_pct": 15.0,
                    "extract_bias_pct": 5.0,
                    "aero_normal_speed": 1,
                    "aero_boost_speed": 2,
                    "aero_high_speed": 3,
                    "aero_max_speed": 3,
                    "pm2_5_hysteresis_ug_m3": 2.0,
                    "voc_hysteresis_index": 10.0,
                    "nox_hysteresis_index": 5.0,
                    "temperature_hysteresis_celsius": 0.5,
                    "pm2_5_boost_confirmation_seconds": 60.0,
                    "state_minimum_hold_seconds": 120.0,
                    "boost_decay_seconds": 180.0,
                    "sensor_fallback_supply_pct": 55.0,
                    "sensor_fallback_extract_pct": 60.0,
                    "aero_sensor_fallback_speed": 2,
                }
            )
            replaced = runtime.replace_configuration(payload)
            self.assertEqual(replaced["revision"], 2)
            self.assertTrue(replaced["dynamics_reset"])
            self.assertFalse(replaced["actuation_supported"])
            self.assertEqual(runtime.policy.tuning.normal_air_request_pct, 30.0)
            self.assertEqual(runtime.configuration()["revision"], 2)
            runtime.close()

    def test_invalid_replace_never_increments_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.sqlite3"
            store = SqliteControlEngineStore(path, initial_config=ControlEngineConfig())
            runtime = PersistentControlEngineEvaluator(store)
            payload = ControlEngineConfig().to_dict()
            payload["policy"]["tuning"]["normal_air_request_pct"] = "30"
            with self.assertRaisesRegex(ValueError, "without type coercion"):
                runtime.replace_configuration(payload)
            self.assertEqual(runtime.configuration()["revision"], 1)
            runtime.close()

            reopened = SqliteControlEngineStore(path)
            _config, revision = reopened.load()
            self.assertEqual(revision, 1)
            reopened.close()

    def test_configuration_has_no_actuation_enable_field(self) -> None:
        payload = ControlEngineConfig().to_dict()
        self.assertNotIn("actuation_enabled", payload)
        self.assertNotIn("actuation_supported", payload)


if __name__ == "__main__":
    unittest.main()
