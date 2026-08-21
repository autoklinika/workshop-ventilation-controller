from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_safe_shutdown_peripherals_cm5.py"
HARNESS = ROOT / "tools" / "install_validate_safe_shutdown_peripherals_cm5.sh"


class SafeShutdownPeripheralsCm5ValidationTests(unittest.TestCase):
    def _load_validator(self):
        spec = importlib.util.spec_from_file_location("safe_shutdown_validator", VALIDATOR)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec is not None else None)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_validator_is_importable_and_requires_explicit_active_test_confirmation(self) -> None:
        module = self._load_validator()
        parser = module.build_parser()
        args = parser.parse_args([])
        self.assertFalse(args.confirm_active_output_test)
        confirmed = parser.parse_args(["--confirm-active-output-test"])
        self.assertTrue(confirmed.confirm_active_output_test)

    def test_validator_executes_exact_pr77_pre_poweroff_path_without_host_power_action(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("agent._prepare_peripherals_for_poweroff()", source)
        self.assertIn("command_launcher=launched.append", source)
        self.assertIn('"host_power_executed": False', source)
        self.assertIn("if launched:", source)
        self.assertNotIn("agent._execute_action(", source)
        self.assertNotIn('subprocess.run(["systemctl", "poweroff"', source)
        self.assertNotIn('subprocess.run(["systemctl", "reboot"', source)
        self.assertNotIn("HostPowerClient", source)

    def test_final_state_requires_stop_zero_known_and_confirmed_aero_speed_zero(self) -> None:
        module = self._load_validator()
        good = {
            "ok": True,
            "state": {
                "mode": "STOP",
                "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
                "output_state_known": True,
                "aero_bus": {
                    "ready": True,
                    "worker_alive": True,
                    "online": True,
                    "usable": True,
                    "last_control_result": {
                        "kind": "speed",
                        "target_value": 0,
                        "state": "succeeded",
                    },
                },
            },
        }
        state = module._require_final_safe_state(good)
        self.assertEqual(state["mode"], "STOP")

        bad_fan = {**good, "state": {**good["state"], "setpoints": {"supply_voltage": 0.0, "extract_voltage": 1.0}}}
        with self.assertRaises(module.ValidationError):
            module._require_final_safe_state(bad_fan)

        bad_aero = {
            **good,
            "state": {
                **good["state"],
                "aero_bus": {
                    **good["state"]["aero_bus"],
                    "last_control_result": {
                        "kind": "speed",
                        "target_value": 0,
                        "state": "failed",
                    },
                },
            },
        }
        with self.assertRaises(module.ValidationError):
            module._require_final_safe_state(bad_aero)

    def test_shell_harness_has_valid_bash_syntax_and_no_power_or_restart_action(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("BRANCH=agent/cm5-shutdown-alert-ai-stage1", source)
        self.assertIn("EXPECTED_BASE=c76dde9aeacbb15625298a4a6d19d3dfeca8cb2f", source)
        self.assertIn("git worktree add --detach", source)
        self.assertIn('PYTHONPATH="$WT/src" python3 "$WT/tools/validate_safe_shutdown_peripherals_cm5.py"', source)
        self.assertIn("CORE_PID_AFTER", source)
        self.assertIn("POWER_PID_AFTER", source)
        self.assertIn("peripherals intentionally remain OFF", source)
        self.assertNotIn("systemctl restart", source)
        self.assertNotIn("systemctl stop", source)
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertNotIn("git merge", source)
        self.assertNotIn("git switch", source)
        self.assertNotIn("git checkout", source)


if __name__ == "__main__":
    unittest.main()
