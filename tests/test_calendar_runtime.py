from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from ventilation_core.application.service import VentilationService
from ventilation_core.calendar import CalendarEngine, default_calendar_config
from ventilation_core.ctl import build_request
from ventilation_core.domain.models import FanSetpoints
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.infrastructure.sqlite_calendar_store import SqliteCalendarStore
from ventilation_core.runtime.server import CoreServer


class FakeActuator:
    def __init__(self) -> None:
        self.ready = True
        self.last_error = None
        self.applied: list[FanSetpoints] = []
        self.stop_calls = 0

    def apply(self, setpoints: FanSetpoints) -> None:
        self.applied.append(setpoints)

    def stop_all(self) -> None:
        self.stop_calls += 1

    def health_check(self) -> None:
        return

    def recover(self) -> None:
        self.ready = True

    def close(self) -> None:
        return


class CalendarRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_replace_calendar_updates_core_context_without_actuation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteCalendarStore(
                Path(directory) / "automation.sqlite3",
                initial_config=default_calendar_config(),
            )
            engine = CalendarEngine(store)
            actuator = FakeActuator()
            service = VentilationService(
                actuator=actuator,  # type: ignore[arg-type]
                policy=FanSetpointPolicy(1.0, 10.0),
                calendar_engine=engine,
            )
            server = CoreServer(
                service=service,
                socket_path=Path(directory) / "core.sock",
                health_interval_seconds=1.0,
            )
            config = {
                "schema_version": 1,
                "timezone": "Europe/Warsaw",
                "profiles": [
                    {
                        "profile_id": "WORK",
                        "mode": "AUTO",
                        "preventilation_minutes": 30,
                        "purge_minutes": 30,
                        "minimum_supply_pct": 25,
                        "minimum_extract_pct": 30,
                    }
                ],
                "rules": [
                    {
                        "rule_id": "MON_FRI",
                        "kind": "WEEKLY",
                        "profile_id": "WORK",
                        "weekdays": [1, 2, 3, 4, 5],
                        "start_local": "07:00",
                        "end_local": "17:00",
                    }
                ],
            }
            response = await server._dispatch(  # noqa: SLF001
                {"command": "calendar-replace", "config": config}
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["calendar"]["revision"], 2)
            self.assertEqual(
                response["calendar"]["config"]["profiles"][0]["profile_id"],
                "WORK",
            )
            self.assertEqual(actuator.applied, [])
            self.assertEqual(service.state().setpoints, FanSetpoints.stopped())

            readback = await server._dispatch({"command": "calendar"})  # noqa: SLF001
            self.assertTrue(readback["ok"])
            self.assertEqual(
                readback["calendar"]["config"]["timezone"],
                "Europe/Warsaw",
            )
            service.close()

    async def test_calendar_replace_rejects_non_object_before_service(self) -> None:
        actuator = FakeActuator()
        service = VentilationService(
            actuator=actuator,  # type: ignore[arg-type]
            policy=FanSetpointPolicy(1.0, 10.0),
        )
        with tempfile.TemporaryDirectory() as directory:
            server = CoreServer(
                service=service,
                socket_path=Path(directory) / "core.sock",
                health_interval_seconds=1.0,
            )
            with self.assertRaisesRegex(ValueError, "JSON object"):
                await server._dispatch(  # noqa: SLF001
                    {"command": "calendar-replace", "config": []}
                )
        service.close()


class CalendarCliTest(unittest.TestCase):
    def test_calendar_replace_reads_one_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.json"
            path.write_text(
                json.dumps(default_calendar_config().to_dict()),
                encoding="utf-8",
            )
            request = build_request(
                argparse.Namespace(command="calendar-replace", file=path)
            )
            self.assertEqual(request["command"], "calendar-replace")
            self.assertIsInstance(request["config"], dict)
            self.assertEqual(request["config"]["schema_version"], 1)

    def test_calendar_replace_rejects_json_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "one JSON object"):
                build_request(argparse.Namespace(command="calendar-replace", file=path))


class CalendarDeploymentTest(unittest.TestCase):
    def test_core_systemd_uses_persistent_automation_database(self) -> None:
        unit = Path("deploy/systemd/ventilation-core.service").read_text(encoding="utf-8")
        self.assertIn("StateDirectory=workshop-ventilation", unit)
        self.assertIn(
            "--automation-db /var/lib/workshop-ventilation/automation.sqlite3",
            unit,
        )


if __name__ == "__main__":
    unittest.main()
