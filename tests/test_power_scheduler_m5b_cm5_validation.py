from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "validate_power_scheduler_m5b_cm5.py"
HARNESS = ROOT / "tools" / "install_validate_power_scheduler_m5b_cm5.sh"


class PowerSchedulerM5BCm5ValidationTest(unittest.TestCase):
    def test_validator_is_valid_python_and_uses_scheduler_plus_real_host_power_client(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("PowerScheduler", source)
        self.assertIn("HostPowerClient", source)
        self.assertIn("execute_scheduled_shutdown", source)
        self.assertIn('action == "shutdown"', source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("os.system", source)

    def test_prepare_persists_boot_rtc_and_host_power_evidence_before_poweroff(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn('"before_boot_id"', source)
        self.assertIn('"expected_wake_epoch"', source)
        self.assertIn('"rtc_verified"', source)
        self.assertIn('"host_power_accepted"', source)
        self.assertIn("os.fsync", source)
        self.assertIn("os.sync()", source)
        self.assertIn("time.sleep(60)", source)

    def test_verify_requires_new_boot_near_programmed_rtc_wake_and_consumed_alarm(self) -> None:
        source = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("current_boot_id != before_boot_id", source)
        self.assertIn("estimated_boot_epoch", source)
        self.assertIn("BOOT_TIME_TOLERANCE_SECONDS = 120", source)
        self.assertIn("rtc.read_epoch() is None", source)
        self.assertIn("M5B full poweroff -> RTC wake cycle verified", source)

    def test_shell_harness_has_valid_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(HARNESS)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_harness_requires_two_explicit_real_poweroff_gates(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('M5B_ALLOW_REAL_POWEROFF:-}" = "YES"', source)
        self.assertIn('M5B_LAB_MODE:-}" = "1"', source)
        self.assertIn("WARNING: this test will call the real wvc-host-power shutdown path", source)

    def test_prepare_has_no_exit_trap_that_can_clear_rtc_during_shutdown(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertNotIn("trap cleanup EXIT", source)
        self.assertNotIn("trap - EXIT", source)
        prepare = source.split("prepare() {", 1)[1].split("verify() {", 1)[0]
        self.assertIn("set +e", prepare)
        self.assertIn("validate_power_scheduler_m5b_cm5.py\" prepare", prepare)
        self.assertIn("systemctl restart wvc-host-power.service", prepare)

    def test_harness_never_calls_system_power_action_directly(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertNotIn("systemctl poweroff", source)
        self.assertNotIn("systemctl reboot", source)
        self.assertNotIn("shutdown -h", source)
        self.assertIn("wvc-host-power.service", source)

    def test_verify_requires_production_main_and_host_power_domain_on_then_cleans_test_state(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        verify = source.split("verify() {", 1)[1].split('case "$MODE"', 1)[0]
        self.assertIn("require_main", verify)
        self.assertIn("require_services", verify)
        self.assertIn("12 V domain ON", verify)
        self.assertIn("cleanup_worktree", verify)
        self.assertIn('sudo rm -rf "$STATE_DIR"', verify)

    def test_m5b_is_pinned_to_known_production_main(self) -> None:
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8", source)
        self.assertIn("M5B_EXPECTED_BRANCH_SHA", source)
        self.assertIn('git fetch origin main "$BRANCH"', source)


if __name__ == "__main__":
    unittest.main()
