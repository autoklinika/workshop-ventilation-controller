from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "run_control_engine_scenario.py"
SCENARIO = ROOT / "config" / "control-engine-scenarios" / "lab-dynamics-v1.json"
RUNNER = ROOT / "src" / "ventilation_core" / "application" / "control_engine_scenario.py"


class ControlEngineScenarioCliTest(unittest.TestCase):
    def test_versioned_lab_scenario_replays_expected_dynamics(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(SCENARIO), "--compact"],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["actuation_supported"])
        self.assertEqual(payload["policy_version"], "scenario-lab-only-v1")
        self.assertEqual(len(payload["steps"]), 7)

        def zone(step_index: int, address: int) -> dict:
            return next(
                row
                for row in payload["steps"][step_index]["shadow"]["zones"]
                if row["sensor_address"] == address
            )

        self.assertEqual(zone(0, 1)["air_quality_level"], "NORMAL")
        self.assertEqual(zone(1, 1)["dynamics_transition_reason"], "ESCALATION_CONFIRMING")
        self.assertEqual(zone(2, 1)["air_quality_level"], "BOOST")
        self.assertEqual(zone(2, 1)["dynamics_transition_reason"], "ESCALATION_CONFIRMED")
        self.assertEqual(zone(3, 1)["air_quality_level"], "HIGH")
        self.assertEqual(zone(3, 1)["air_quality_driver"], "VOC")
        self.assertEqual(zone(4, 1)["dynamics_transition_reason"], "MINIMUM_HOLD")
        self.assertEqual(zone(5, 1)["dynamics_transition_reason"], "DEESCALATION_DECAY")
        self.assertEqual(zone(6, 1)["air_quality_level"], "NORMAL")
        self.assertEqual(zone(6, 1)["dynamics_transition_reason"], "DEESCALATION_CONFIRMED")

        for item in payload["steps"]:
            self.assertFalse(item["shadow"]["actuation_supported"])
            for row in item["shadow"]["zones"]:
                self.assertIsNone(row["proposed_supply_voltage"])
                self.assertIsNone(row["proposed_extract_voltage"])

    def test_runner_has_no_physical_actuation_boundary(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        forbidden = (
            "subprocess",
            "systemctl",
            "vcgencmd",
            "HostPower",
            "host_power",
            "Gp8403",
            "gp8403",
            "AeroControlExecutor",
            "gpio",
            "/dev/tty",
            "shutdown",
            "reboot",
            "poweroff",
        )
        for token in forbidden:
            self.assertNotIn(token, text)
        self.assertIn("actuation_supported", text)
        self.assertIn("proposed_supply_voltage", text)
        self.assertIn("proposed_extract_voltage", text)

    def test_cli_rejects_malformed_json(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        bad = ROOT / "tests" / ".tmp-control-engine-scenario-invalid.json"
        try:
            bad.write_text("{not-json", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(TOOL), str(bad)],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("CONTROL_ENGINE_SCENARIO_FAIL", proc.stderr)
        finally:
            bad.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
