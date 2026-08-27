from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_power_scheduler_m5a_cm5.py"
HARNESS = ROOT / "tools" / "install_validate_power_scheduler_m5a_cm5.sh"


class PowerSchedulerM5ACm5ValidationTest(unittest.TestCase):
    def test_validator_is_non_actuating_and_uses_exact_shutdown_intent(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        compile(source, str(VALIDATOR), "exec")
        self.assertIn("execute_scheduled_shutdown", source)
        self.assertIn('host_power.actions == ["shutdown"]', source)
        self.assertIn('"physical_power_action": False', source)
        self.assertIn('"real_host_power_socket_used": False', source)
        self.assertNotIn("/run/wvc-host-power", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("poweroff", source)
        self.assertNotIn("reboot", source)
        self.assertNotIn("sudo halt", source)

    def test_shell_harness_has_valid_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_harness_is_pinned_and_does_not_restart_or_power_host(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8", source)
        self.assertIn('EXPECTED_BRANCH_SHA="${M5A_EXPECTED_BRANCH_SHA:-}"', source)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', source)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", source)
        self.assertIn("CORE_PID_BEFORE", source)
        self.assertIn("HOST_POWER_PID_BEFORE", source)
        self.assertNotIn("systemctl restart", source)
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertNotIn("sudo halt", source)

    def test_harness_requires_empty_rtc_before_and_after(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('CURRENT_ALARM="$(cat "$WAKEALARM")"', source)
        self.assertIn("RTC wakealarm already armed", source)
        self.assertIn('FINAL_ALARM="$(cat "$WAKEALARM")"', source)
        self.assertIn("validator left RTC wakealarm armed", source)
        self.assertIn("echo 0 >", source)

    def test_harness_cleans_privileged_bytecode_before_worktree_remove(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("find \"$WT\" -type d -name __pycache__", source)
        self.assertIn("sudo rm -rf \"$WT\"", source)


if __name__ == "__main__":
    unittest.main()
