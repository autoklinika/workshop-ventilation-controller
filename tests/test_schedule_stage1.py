from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ventilation_core.application.schedule_controller import (
    CoreScheduleManager,
    UnavailableScheduleManager,
)
from ventilation_core.application.service import VentilationService
from ventilation_core.ctl import build_request
from ventilation_core.domain.models import FanSetpoints
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.domain.schedule import (
    ScheduleExpectation,
    ScheduleWindow,
    evaluate_schedule,
    parse_local_time,
    validate_windows,
)
from ventilation_core.infrastructure.sqlite_schedule_store import SqliteScheduleStore
from ventilation_core.runtime.server import CoreServer


class MemoryScheduleStore:
    def __init__(self, windows: tuple[ScheduleWindow, ...] = ()) -> None:
        self.windows = windows
        self.closed = False

    def list_windows(self, zone: str | None = None) -> tuple[ScheduleWindow, ...]:
        if zone is None:
            return self.windows
        return tuple(window for window in self.windows if window.zone == zone)

    def replace_zone(self, zone: str, windows: tuple[ScheduleWindow, ...]) -> tuple[ScheduleWindow, ...]:
        retained = tuple(window for window in self.windows if window.zone != zone)
        assigned = tuple(
            ScheduleWindow(
                window_id=index + 1,
                zone=window.zone,
                weekday=window.weekday,
                start_minute=window.start_minute,
                end_minute=window.end_minute,
                expectation=window.expectation,
                enabled=window.enabled,
                label=window.label,
            )
            for index, window in enumerate(windows)
        )
        self.windows = retained + assigned
        return assigned

    def close(self) -> None:
        self.closed = True


class BrokenScheduleStore(MemoryScheduleStore):
    def list_windows(self, zone: str | None = None) -> tuple[ScheduleWindow, ...]:
        del zone
        raise RuntimeError("database unavailable")


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


class ScheduleDomainTest(unittest.TestCase):
    def test_weekday_window_and_outside_default(self) -> None:
        window = ScheduleWindow.from_payload(
            "zone-1",
            {
                "weekday": 1,
                "start_local": "07:00",
                "end_local": "15:00",
                "expectation": "OCCUPIED_EXPECTED",
            },
        )
        occupied = evaluate_schedule(
            (window,),
            ("zone-1", "zone-2"),
            now_utc=datetime(2026, 8, 17, 5, 30, tzinfo=timezone.utc),
        )
        self.assertTrue(occupied.available)
        self.assertEqual(occupied.zones[0].expectation, ScheduleExpectation.OCCUPIED_EXPECTED)
        self.assertEqual(occupied.zones[1].expectation, ScheduleExpectation.UNOCCUPIED_EXPECTED)

    def test_overnight_window_matches_next_day(self) -> None:
        window = ScheduleWindow(
            zone="zone-1",
            weekday=5,
            start_minute=parse_local_time("22:00"),
            end_minute=parse_local_time("02:00"),
        )
        state = evaluate_schedule(
            (window,),
            ("zone-1",),
            now_utc=datetime(2026, 8, 21, 22, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(state.zones[0].expectation, ScheduleExpectation.OCCUPIED_EXPECTED)

    def test_overlapping_enabled_windows_are_rejected(self) -> None:
        windows = (
            ScheduleWindow("zone-1", 1, 7 * 60, 12 * 60),
            ScheduleWindow("zone-1", 1, 11 * 60, 15 * 60),
        )
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            validate_windows(windows)

    def test_dst_spring_forward_keeps_wall_clock_semantics(self) -> None:
        window = ScheduleWindow("zone-1", 7, 60, 4 * 60)
        before_jump = evaluate_schedule(
            (window,),
            ("zone-1",),
            now_utc=datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc),
        )
        after_jump = evaluate_schedule(
            (window,),
            ("zone-1",),
            now_utc=datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(before_jump.zones[0].expectation, ScheduleExpectation.OCCUPIED_EXPECTED)
        self.assertEqual(after_jump.zones[0].expectation, ScheduleExpectation.OCCUPIED_EXPECTED)

    def test_dst_fall_back_matches_both_repeated_0230_instants(self) -> None:
        window = ScheduleWindow("zone-1", 7, 2 * 60, 3 * 60)
        first_fold = evaluate_schedule(
            (window,),
            ("zone-1",),
            now_utc=datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc),
        )
        second_fold = evaluate_schedule(
            (window,),
            ("zone-1",),
            now_utc=datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(first_fold.zones[0].expectation, ScheduleExpectation.OCCUPIED_EXPECTED)
        self.assertEqual(second_fold.zones[0].expectation, ScheduleExpectation.OCCUPIED_EXPECTED)


class SchedulePersistenceTest(unittest.TestCase):
    def test_schedule_survives_store_restart_and_zone_replace_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "automation.sqlite3"
            store = SqliteScheduleStore(path)
            first = store.replace_zone(
                "zone-1",
                (
                    ScheduleWindow("zone-1", 1, 7 * 60, 15 * 60, label="Zmiana 1"),
                    ScheduleWindow("zone-1", 2, 7 * 60, 15 * 60, label="Zmiana 1"),
                ),
            )
            self.assertEqual(len(first), 2)
            self.assertTrue(all(window.window_id is not None for window in first))
            store.close()

            store = SqliteScheduleStore(path)
            restored = store.list_windows("zone-1")
            self.assertEqual(len(restored), 2)
            self.assertEqual(restored[0].label, "Zmiana 1")
            store.replace_zone("zone-1", (ScheduleWindow("zone-1", 3, 8 * 60, 12 * 60),))
            self.assertEqual(len(store.list_windows("zone-1")), 1)
            store.close()

    def test_invalid_replacement_does_not_delete_existing_zone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SqliteScheduleStore(Path(directory) / "automation.sqlite3")
            store.replace_zone("zone-1", (ScheduleWindow("zone-1", 1, 7 * 60, 15 * 60),))
            with self.assertRaises(ValueError):
                store.replace_zone(
                    "zone-1",
                    (
                        ScheduleWindow("zone-1", 1, 7 * 60, 12 * 60),
                        ScheduleWindow("zone-1", 1, 11 * 60, 15 * 60),
                    ),
                )
            self.assertEqual(len(store.list_windows("zone-1")), 1)
            store.close()


class ScheduleManagerTest(unittest.TestCase):
    def test_store_failure_exposes_unknown_not_unoccupied(self) -> None:
        manager = CoreScheduleManager(BrokenScheduleStore(), zones=("zone-1", "zone-2"))
        state = manager.current_state(datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc))
        self.assertFalse(state.available)
        self.assertEqual(state.zones[0].expectation, ScheduleExpectation.UNKNOWN)
        self.assertEqual(state.zones[1].expectation, ScheduleExpectation.UNKNOWN)
        self.assertIn("database unavailable", state.last_error)
        manager.close()

    def test_explicit_unavailable_manager_rejects_writes(self) -> None:
        manager = UnavailableScheduleManager("read-only failure")
        self.assertFalse(manager.current_state().available)
        with self.assertRaisesRegex(RuntimeError, "read-only failure"):
            manager.replace_zone("zone-1", ())


class ScheduleCoreApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_replace_schedule_updates_core_state_without_actuating_fans(self) -> None:
        actuator = FakeActuator()
        store = MemoryScheduleStore()
        manager = CoreScheduleManager(store)
        service = VentilationService(
            actuator=actuator,  # type: ignore[arg-type]
            policy=FanSetpointPolicy(1.0, 10.0),
            schedule_manager=manager,
        )
        with tempfile.TemporaryDirectory() as directory:
            server = CoreServer(
                service=service,
                socket_path=Path(directory) / "core.sock",
                health_interval_seconds=1.0,
            )
            response = await server._dispatch(  # noqa: SLF001
                {
                    "command": "schedule-replace",
                    "zone": "zone-1",
                    "windows": [
                        {
                            "weekday": 1,
                            "start_local": "07:00",
                            "end_local": "15:00",
                            "expectation": "OCCUPIED_EXPECTED",
                            "enabled": True,
                            "label": "Poniedzialek",
                        }
                    ],
                }
            )
            self.assertTrue(response["ok"])
            self.assertEqual(len(response["schedule"]["windows"]), 1)
            self.assertEqual(actuator.applied, [])
            self.assertEqual(service.state().setpoints, FanSetpoints.stopped())
            readback = await server._dispatch({"command": "schedule"})  # noqa: SLF001
            self.assertTrue(readback["ok"])
            self.assertEqual(readback["schedule"]["timezone"], "Europe/Warsaw")
        service.close()


class ScheduleCtlTest(unittest.TestCase):
    def test_schedule_replace_reads_json_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.json"
            path.write_text(
                json.dumps([{"weekday": 1, "start_local": "07:00", "end_local": "15:00"}]),
                encoding="utf-8",
            )
            request = build_request(
                argparse.Namespace(command="schedule-replace", zone="zone-1", file=path)
            )
            self.assertEqual(request["command"], "schedule-replace")
            self.assertEqual(request["zone"], "zone-1")
            self.assertEqual(len(request["windows"]), 1)


class ScheduleDeploymentTest(unittest.TestCase):
    def test_core_systemd_uses_persistent_automation_database(self) -> None:
        unit = Path("deploy/systemd/ventilation-core.service").read_text(encoding="utf-8")
        self.assertIn("StateDirectory=workshop-ventilation", unit)
        self.assertIn("--automation-db /var/lib/workshop-ventilation/automation.sqlite3", unit)


if __name__ == "__main__":
    unittest.main()
