from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ventilation_core.application.control_engine_bootstrap import build_control_engine_evaluator
from ventilation_core.application.control_engine_runtime import PersistentControlEngineEvaluator
from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.runtime.control_engine_server import ControlEngineCoreServer


class DummyState:
    def to_dict(self) -> dict[str, object]:
        return {"shadow_automation": {"actuation_supported": False}}


class DummyControlService:
    def __init__(self) -> None:
        self.payload = {
            "revision": 1,
            "config": ControlEngineConfig().to_dict(),
            "actuation_supported": False,
        }
        self.replacements: list[dict[str, object]] = []

    def control_engine_configuration(self):
        return self.payload

    def replace_control_engine_configuration(self, payload):
        self.replacements.append(payload)
        self.payload = {
            "revision": 2,
            "config": payload,
            "actuation_supported": False,
            "dynamics_reset": True,
        }
        return self.payload

    def state(self):
        return DummyState()


class ControlEngineBootstrapTest(unittest.TestCase):
    def test_successful_bootstrap_is_persistent_and_non_actuating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.sqlite3"
            evaluator = build_control_engine_evaluator(path)
            self.assertIsInstance(evaluator, PersistentControlEngineEvaluator)
            metadata = evaluator.configuration()  # type: ignore[attr-defined]
            self.assertEqual(metadata["revision"], 1)
            self.assertFalse(metadata["actuation_supported"])
            self.assertTrue(path.exists())
            evaluator.close()  # type: ignore[attr-defined]

    def test_database_failure_falls_back_to_empty_nonpersistent_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            # Passing an existing directory as sqlite file path forces sqlite open failure.
            evaluator = build_control_engine_evaluator(Path(directory))
            self.assertIsInstance(evaluator, PolicyShadowAutomationEvaluator)
            self.assertFalse(evaluator.policy.tuning.outputs_configured)  # type: ignore[attr-defined]
            self.assertFalse(evaluator.policy.tuning.dynamics_configured)  # type: ignore[attr-defined]


class ControlEngineSocketBoundaryTest(unittest.IsolatedAsyncioTestCase):
    def server(self, service) -> ControlEngineCoreServer:
        return ControlEngineCoreServer(
            service=service,  # type: ignore[arg-type]
            socket_path=Path("/tmp/not-used-control-engine-test.sock"),
            health_interval_seconds=1.0,
        )

    async def test_read_configuration_is_read_only(self) -> None:
        service = DummyControlService()
        response = await self.server(service)._dispatch({"command": "control-engine"})  # noqa: SLF001
        self.assertTrue(response["ok"])
        self.assertEqual(response["control_engine"]["revision"], 1)
        self.assertFalse(response["control_engine"]["actuation_supported"])
        self.assertEqual(service.replacements, [])

    async def test_replace_requires_json_object_and_returns_state(self) -> None:
        service = DummyControlService()
        payload = ControlEngineConfig().to_dict()
        response = await self.server(service)._dispatch(  # noqa: SLF001
            {"command": "control-engine-replace", "config": payload}
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["control_engine"]["revision"], 2)
        self.assertTrue(response["control_engine"]["dynamics_reset"])
        self.assertFalse(response["control_engine"]["actuation_supported"])
        self.assertEqual(service.replacements, [payload])
        self.assertFalse(response["state"]["shadow_automation"]["actuation_supported"])

        with self.assertRaisesRegex(ValueError, "JSON object"):
            await self.server(service)._dispatch(  # noqa: SLF001
                {"command": "control-engine-replace", "config": []}
            )


if __name__ == "__main__":
    unittest.main()
