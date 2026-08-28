from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "run_control_engine_matrix.py"
MATRIX = ROOT / "config" / "control-engine-scenarios" / "lab-cross-domain-matrix-v1.json"
RUNNER = ROOT / "src" / "ventilation_core" / "application" / "control_engine_matrix.py"


class ControlEngineMatrixCliTest(unittest.TestCase):
    def test_versioned_matrix_summary_is_stable_and_non_actuating(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(MATRIX),
                "--summary",
                "--compact",
            ],
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
        self.assertEqual(payload["case_count"], 768)
        self.assertEqual(
            payload["dimensions"],
            ["calendar", "air_quality", "temperature", "fault"],
        )
        self.assertEqual(
            payload["status_counts"],
            {
                "BLOCKED_SAFETY": 384,
                "DEGRADED": 288,
                "READY": 96,
            },
        )
        self.assertEqual(payload["safety_blocked_cases"], 384)
        self.assertEqual(payload["sensor_fallback_cases"], 192)
        self.assertEqual(
            payload["zone1_automation_state_counts"],
            {
                "BOOST": 96,
                "EMERGENCY_VENT": 48,
                "FAULT": 576,
                "NORMAL": 4,
                "OFF": 8,
                "PREVENTILATION": 8,
                "PURGE": 8,
                "STANDBY": 8,
                "TEMP_LIMIT": 12,
            },
        )
        self.assertEqual(
            payload["zone2_automation_state_counts"],
            {
                "FAULT": 576,
                "NORMAL": 64,
                "OFF": 32,
                "PREVENTILATION": 32,
                "PURGE": 32,
                "STANDBY": 32,
            },
        )

    def test_matrix_runner_has_no_physical_control_boundary(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        for forbidden in (
            "import subprocess",
            "import socket",
            "import os",
            "systemctl",
            "/dev/",
            "ventilation_core.infrastructure",
            "AeroControlExecutor(",
            "Gp8403(",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("ControlEngineScenarioRunner", text)
        self.assertIn("actuation_supported", text)
        self.assertIn("proposed_supply_voltage", text)
        self.assertIn("proposed_extract_voltage", text)

    def test_cli_rejects_malformed_json(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        bad = ROOT / "tests" / ".tmp-control-engine-matrix-invalid.json"
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
            self.assertIn("CONTROL_ENGINE_MATRIX_FAIL", proc.stderr)
        finally:
            bad.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
