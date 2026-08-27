from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ventilation_core.application.control_engine_bootstrap import build_control_engine_evaluator
from ventilation_core.application.control_engine_runtime import PersistentControlEngineEvaluator
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.infrastructure.sqlite_control_engine_store import SqliteControlEngineStore


def minimal_state() -> CoreState:
    return CoreState(
        mode=VentilationMode.STOP,
        setpoints=FanSetpoints.stopped(),
        hardware_ready=True,
        output_state_known=True,
    )


class ControlEngineRevisionTelemetryTest(unittest.TestCase):
    def test_persistent_evaluator_publishes_revision_in_shadow_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteControlEngineStore(
                Path(directory) / "automation.sqlite3",
                initial_config=ControlEngineConfig(),
            )
            runtime = PersistentControlEngineEvaluator(store)
            first = runtime.evaluate(minimal_state())
            self.assertEqual(first.configuration_revision, 1)
            self.assertTrue(first.configuration_persistent)
            self.assertFalse(first.actuation_supported)

            runtime.replace_configuration(ControlEngineConfig().to_dict())
            second = runtime.evaluate(minimal_state())
            self.assertEqual(second.configuration_revision, 2)
            self.assertTrue(second.configuration_persistent)
            self.assertFalse(second.actuation_supported)
            runtime.close()

    def test_fail_safe_nonpersistent_bootstrap_is_explicit_in_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evaluator = build_control_engine_evaluator(Path(directory))
            result = evaluator.evaluate(minimal_state())
            self.assertIsNone(result.configuration_revision)
            self.assertFalse(result.configuration_persistent)
            self.assertFalse(result.actuation_supported)

    def test_serialized_shadow_contract_exposes_persistence_without_actuation_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteControlEngineStore(
                Path(directory) / "automation.sqlite3",
                initial_config=ControlEngineConfig(),
            )
            runtime = PersistentControlEngineEvaluator(store)
            payload = runtime.evaluate(minimal_state()).to_dict()
            self.assertEqual(payload["configuration_revision"], 1)
            self.assertTrue(payload["configuration_persistent"])
            self.assertFalse(payload["actuation_supported"])
            self.assertNotIn("actuation_enabled", payload)
            runtime.close()


if __name__ == "__main__":
    unittest.main()
