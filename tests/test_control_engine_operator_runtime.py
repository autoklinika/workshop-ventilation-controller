from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ventilation_core.application.control_engine_runtime import PersistentControlEngineEvaluator
from ventilation_core.ctl import build_parser, build_request
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.infrastructure.sqlite_control_engine_store import SqliteControlEngineStore
from ventilation_core.runtime.control_engine_server import ControlEngineCoreServer


MANUAL = {
    "mode": "MANUAL",
    "manual_supply_pct": 20.0,
    "manual_extract_pct": 25.0,
    "manual_aero_speed": 1,
}


class DummyState:
    def to_dict(self) -> dict[str, object]:
        return {"shadow_automation": {"actuation_supported": False}}


class DummyOperatorService:
    def __init__(self) -> None:
        self.operator = {
            "revision": 0,
            "intent": {
                "mode": "AUTO",
                "manual_supply_pct": None,
                "manual_extract_pct": None,
                "manual_aero_speed": None,
            },
            "persistent": False,
            "reset_on_core_restart": True,
            "actuation_supported": False,
        }
        self.replacements: list[dict[str, object]] = []

    def control_engine_operator_state(self):
        return self.operator

    def replace_control_engine_operator_intent(self, payload):
        self.replacements.append(payload)
        self.operator = {
            "revision": self.operator["revision"] + 1,
            "intent": payload,
            "persistent": False,
            "reset_on_core_restart": True,
            "actuation_supported": False,
        }
        return self.operator

    def state(self):
        return DummyState()


class OperatorRuntimePersistenceTest(unittest.TestCase):
    def runtime(self, path: Path) -> PersistentControlEngineEvaluator:
        return PersistentControlEngineEvaluator(
            SqliteControlEngineStore(path, initial_config=ControlEngineConfig())
        )

    def test_operator_intent_is_volatile_and_restarts_in_auto(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.sqlite3"
            runtime = self.runtime(path)
            initial = runtime.operator_state()
            self.assertEqual(initial["revision"], 0)
            self.assertEqual(initial["intent"]["mode"], "AUTO")
            self.assertFalse(initial["persistent"])
            self.assertTrue(initial["reset_on_core_restart"])
            self.assertFalse(initial["actuation_supported"])

            manual = runtime.replace_operator_intent(MANUAL)
            self.assertEqual(manual["revision"], 1)
            self.assertEqual(manual["intent"], MANUAL)
            runtime.close()

            restarted = self.runtime(path)
            after_restart = restarted.operator_state()
            self.assertEqual(after_restart["revision"], 0)
            self.assertEqual(after_restart["intent"]["mode"], "AUTO")
            self.assertIsNone(after_restart["intent"]["manual_supply_pct"])
            restarted.close()

    def test_config_hot_reload_does_not_silently_change_operator_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.sqlite3"
            runtime = self.runtime(path)
            runtime.replace_operator_intent(MANUAL)
            config = ControlEngineConfig().to_dict()
            config["policy"]["version"] = "operator-hot-reload-test"
            replaced = runtime.replace_configuration(config)
            self.assertTrue(replaced["dynamics_reset"])
            operator = runtime.operator_state()
            self.assertEqual(operator["revision"], 1)
            self.assertEqual(operator["intent"], MANUAL)
            runtime.close()

    def test_invalid_operator_intent_never_increments_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.runtime(Path(directory) / "automation.sqlite3")
            with self.assertRaises(ValueError):
                runtime.replace_operator_intent(
                    {
                        "mode": "MANUAL",
                        "manual_supply_pct": 20,
                        "manual_extract_pct": 25,
                        "manual_aero_speed": 4,
                    }
                )
            self.assertEqual(runtime.operator_state()["revision"], 0)
            self.assertEqual(runtime.operator_state()["intent"]["mode"], "AUTO")
            runtime.close()


class OperatorSocketBoundaryTest(unittest.IsolatedAsyncioTestCase):
    def server(self, service) -> ControlEngineCoreServer:
        return ControlEngineCoreServer(
            service=service,  # type: ignore[arg-type]
            socket_path=Path("/tmp/not-used-operator-test.sock"),
            health_interval_seconds=1.0,
        )

    async def test_operator_read_is_non_actuating(self) -> None:
        service = DummyOperatorService()
        response = await self.server(service)._dispatch(  # noqa: SLF001
            {"command": "control-engine-operator"}
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["operator"]["intent"]["mode"], "AUTO")
        self.assertFalse(response["operator"]["actuation_supported"])
        self.assertEqual(service.replacements, [])

    async def test_operator_replace_has_narrow_envelope_and_returns_shadow_state(self) -> None:
        service = DummyOperatorService()
        response = await self.server(service)._dispatch(  # noqa: SLF001
            {"command": "control-engine-operator-replace", "operator": MANUAL}
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["operator"]["intent"], MANUAL)
        self.assertFalse(response["operator"]["actuation_supported"])
        self.assertEqual(service.replacements, [MANUAL])
        self.assertFalse(response["state"]["shadow_automation"]["actuation_supported"])

        with self.assertRaisesRegex(ValueError, "JSON object"):
            await self.server(service)._dispatch(  # noqa: SLF001
                {"command": "control-engine-operator-replace", "operator": []}
            )


class OperatorCliContractTest(unittest.TestCase):
    def test_cli_builds_separate_shadow_operator_command(self) -> None:
        parser = build_parser()
        read = build_request(parser.parse_args(["control-engine-operator"]))
        self.assertEqual(read, {"command": "control-engine-operator"})

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual.json"
            path.write_text(json.dumps(MANUAL), encoding="utf-8")
            replace = build_request(
                parser.parse_args(
                    ["control-engine-operator-replace", "--file", str(path)]
                )
            )
        self.assertEqual(
            replace,
            {"command": "control-engine-operator-replace", "operator": MANUAL},
        )
        self.assertNotEqual(replace["command"], "set")
        self.assertNotIn("supply_voltage", replace)
        self.assertNotIn("extract_voltage", replace)


if __name__ == "__main__":
    unittest.main()
