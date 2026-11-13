"""Core-level narrow Unix command contract for Autostart.

No actuator or power-control service is instantiated in this test.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
import unittest

from ventilation_core.infrastructure.sqlite_autostart_store import SqliteAutostartStore
from ventilation_core.runtime.server import CoreServer
from ventilation_core.domain.autostart import default_config


class AutostartCoreRuntimeTests(unittest.TestCase):
    def test_dispatch_roundtrip_is_store_only(self):
        with tempfile.TemporaryDirectory() as td:
            store = SqliteAutostartStore(Path(td) / "automation.sqlite3")
            core = CoreServer(
                service=object(),
                socket_path=Path(td) / "core.sock",
                health_interval_seconds=10,
                autostart_store=store,
            )
            response = asyncio.run(core._dispatch({"command": "autostart", "year": 2026}))
            self.assertTrue(response["ok"])
            self.assertEqual(len(response["autostart"]["days"]), 365)
            self.assertFalse(response["autostart"]["actuation_enabled"])
            self.assertEqual(response["autostart"]["revision"], 1)
            config = default_config()
            config["enabled"] = True
            config["schedule_enabled"] = True
            config["week"][0].update(start_local="08:00", end_local="18:30")
            updated = asyncio.run(core._dispatch({
                "command": "autostart-replace", "year": 2026,
                "config": config, "expected_revision": 1,
            }))
            self.assertEqual(updated["autostart"]["revision"], 2)
            self.assertEqual(updated["autostart"]["config"]["week"][0]["end_local"], "18:30")
            with self.assertRaises(ValueError):
                asyncio.run(core._dispatch({
                    "command": "autostart-replace", "year": 2026,
                    "config": config, "expected_revision": 1,
                }))
            store.close()

    def test_reject_invalid_year_and_disabled_storage(self):
        with tempfile.TemporaryDirectory() as td:
            core = CoreServer(
                service=object(),
                socket_path=Path(td) / "core.sock",
                health_interval_seconds=10,
            )
            with self.assertRaises(RuntimeError):
                asyncio.run(core._dispatch({"command": "autostart", "year": 2026}))
            store = SqliteAutostartStore(Path(td) / "automation.sqlite3")
            valid = CoreServer(
                service=object(),
                socket_path=Path(td) / "core.sock",
                health_interval_seconds=10,
                autostart_store=store,
            )
            for value in (True, "2026", 1900, 2101, None):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        asyncio.run(valid._dispatch({"command": "autostart", "year": value}))
            store.close()


if __name__ == "__main__":
    unittest.main()
