from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ventilation_core import ctl
from ventilation_core.domain.control_engine_config import ControlEngineConfig


class ControlEngineCliTest(unittest.TestCase):
    def test_read_command_is_exact(self) -> None:
        args = ctl.build_parser().parse_args(["control-engine"])
        self.assertEqual(ctl.build_request(args), {"command": "control-engine"})

    def test_replace_reads_one_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control-engine.json"
            config = ControlEngineConfig().to_dict()
            path.write_text(json.dumps(config), encoding="utf-8")
            args = ctl.build_parser().parse_args(
                ["control-engine-replace", "--file", str(path)]
            )
            self.assertEqual(
                ctl.build_request(args),
                {"command": "control-engine-replace", "config": config},
            )

    def test_replace_rejects_json_list_before_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("[]", encoding="utf-8")
            args = ctl.build_parser().parse_args(
                ["control-engine-replace", "--file", str(path)]
            )
            with self.assertRaisesRegex(ValueError, "one JSON object"):
                ctl.build_request(args)

    def test_existing_calendar_replace_contract_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendar.json"
            payload = {"schema_version": 1, "timezone": "Europe/Warsaw", "profiles": [], "rules": []}
            path.write_text(json.dumps(payload), encoding="utf-8")
            args = ctl.build_parser().parse_args(["calendar-replace", "--file", str(path)])
            self.assertEqual(
                ctl.build_request(args),
                {"command": "calendar-replace", "config": payload},
            )


if __name__ == "__main__":
    unittest.main()
