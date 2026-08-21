from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_safe_shutdown_active_to_off_cm5.py"
HARNESS = ROOT / "tools" / "install_validate_safe_shutdown_active_to_off_cm5.sh"


class SafeShutdownActiveToOffCm5ValidationTests(unittest.TestCase):
    def test_validator_is_importable_and_requires_explicit_active_test_confirmation(self) -> None:
        spec = importlib.util.spec_from_file_location("safe_shutdown_active_validator", VALIDATOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("--confirm-active-to-off-test", source)
        self.assertIn('"supply_voltage": 3.0', source)
        self.assertIn('"extract_voltage": 3.0', source)
        self.assertIn('{"command": "aero-airing", "enabled": True}', source)
        self.assertIn('{"command": "aero-speed", "speed": 1}', source)

    def test_validator_executes_exact_pr77_pre_poweroff_path_without_host_power_action(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("agent._prepare_peripherals_for_poweroff()", source)
        self.assertNotIn("agent._execute_action", source)
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertIn('"host_power_executed": False', source)

    def test_validator_requires_real_running_and_stopped_tacho(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("_wait_running_tacho", source)
        self.assertIn("_wait_stopped_tacho", source)
        self.assertIn('supply.get("valid") is True', source)
        self.assertIn('extract.get("valid") is True', source)
        self.assertIn('supply.get("valid") is False', source)
        self.assertIn('extract.get("valid") is False', source)
        self.assertIn("> 100.0", source)

    def test_validator_requires_physical_aero_zero_and_best_effort_cleanup(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('result.get("physical_confirmation") is not True', source)
        self.assertIn('observed.get("fan_1_percent") != 0', source)
        self.assertIn('observed.get("fan_2_percent") != 0', source)
        self.assertIn("_best_effort_off", source)
        self.assertIn('{"command": "stop"}', source)
        self.assertIn('{"command": "aero-airing", "enabled": False}', source)
        self.assertIn('{"command": "aero-speed", "speed": 0}', source)

    def test_shell_harness_has_valid_syntax_and_never_powers_host(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("EXPECTED_BASE=c76dde9aeacbb15625298a4a6d19d3dfeca8cb2f", source)
        self.assertIn("--confirm-active-to-off-test", source)
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertNotIn("systemctl restart", source)


if __name__ == "__main__":
    unittest.main()
