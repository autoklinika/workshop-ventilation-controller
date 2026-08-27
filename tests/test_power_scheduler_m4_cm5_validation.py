from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_power_scheduler_m4_cm5.py"
HARNESS = ROOT / "tools" / "install_validate_power_scheduler_m4_cm5.sh"


class PowerSchedulerM4Cm5ValidationTest(unittest.TestCase):
    def test_python_validator_is_valid_and_has_no_host_power_path(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        compile(source, str(VALIDATOR), "exec")
        self.assertIn("SysfsRtcWakeAlarm", source)
        self.assertIn("PowerScheduler", source)
        self.assertIn("physical_power_action", source)
        self.assertIn("host_power_requested", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("poweroff", source)
        self.assertNotIn("reboot", source)
        self.assertNotIn("halt", source)
        self.assertNotIn("host-power.sock", source)

    def test_shell_harness_has_valid_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_harness_is_pinned_isolated_and_never_restarts_or_powers_host(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8", source)
        self.assertIn('EXPECTED_BRANCH_SHA="${M4_EXPECTED_BRANCH_SHA:-}"', source)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', source)
        self.assertIn('sudo env PYTHONPATH="$WT/src"', source)
        self.assertIn('echo 0 >', source)
        self.assertIn('CORE_PID_AFTER', source)
        self.assertNotIn("systemctl restart", source)
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertNotIn("sudo halt", source)
        self.assertNotIn("host-power.sock", source)

    def test_harness_refuses_to_overwrite_existing_wake_alarm(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('CURRENT_ALARM="$(cat "$WAKEALARM")"', source)
        self.assertIn('RTC wakealarm already armed', source)
        self.assertIn('FINAL_ALARM="$(cat "$WAKEALARM")"', source)
        self.assertIn('validator left RTC wakealarm armed', source)


if __name__ == "__main__":
    unittest.main()
