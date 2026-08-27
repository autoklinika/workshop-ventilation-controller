from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_power_scheduler_m6a_cm5.sh"


class PowerSchedulerM6ACm5ValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HARNESS.read_text(encoding="utf-8")

    def test_harness_has_valid_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_harness_pins_production_main_and_exact_branch_sha(self) -> None:
        self.assertIn(
            "EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8",
            self.text,
        )
        self.assertIn('EXPECTED_BRANCH_SHA="${M6A_EXPECTED_BRANCH_SHA:-}"', self.text)
        self.assertIn('git fetch origin main "$BRANCH"', self.text)
        self.assertIn('BRANCH_SHA="$(git rev-parse "origin/$BRANCH")"', self.text)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', self.text)

    def test_branch_core_explicitly_omits_scheduled_shutdown_opt_in(self) -> None:
        exec_lines = [
            line
            for line in self.text.splitlines()
            if line.startswith("ExecStart=/usr/bin/python3 -m ventilation_core.main")
        ]
        self.assertEqual(len(exec_lines), 1)
        self.assertNotIn("--enable-scheduled-shutdown", exec_lines[0])
        self.assertIn("--power-scheduler-poll-interval 1.0", exec_lines[0])
        self.assertIn("--rtc-agent-socket", exec_lines[0])
        self.assertIn("--host-power-socket", exec_lines[0])

    def test_validator_requires_disabled_non_actuating_runtime_state(self) -> None:
        for expected in (
            '"scheduled_shutdown_enabled": False',
            '"shutdown_ready": False',
            '"rtc_alarm_armed": False',
            '"rtc_alarm_verified": False',
            '"rtc_alarm_value": None',
            '"shutdown_inhibited_reason": "scheduled_shutdown_disabled"',
            '"last_host_power_requested": False',
            '"last_host_power_accepted": False',
            'power.get("worker_alive") is not True',
            'power.get("last_tick_at")',
        ):
            self.assertIn(expected, self.text)

    def test_harness_proves_host_and_rtc_are_unchanged(self) -> None:
        self.assertIn('BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"', self.text)
        self.assertIn('HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"', self.text)
        self.assertIn('WAKEALARM_BEFORE="$(read_wakealarm)"', self.text)
        self.assertIn('[ "$boot_id" = "$BOOT_ID_BEFORE" ]', self.text)
        self.assertIn('[ "$host_pid" = "$HOST_POWER_PID_BEFORE" ]', self.text)
        self.assertIn('[ "$wakealarm" = "$WAKEALARM_BEFORE" ]', self.text)
        self.assertIn('*"12 V domain ON"*', self.text)
        self.assertNotIn("systemctl --no-block poweroff", self.text)
        self.assertNotIn("systemctl --no-block reboot", self.text)
        self.assertNotIn("/usr/bin/systemctl poweroff", self.text)
        self.assertNotIn("/usr/bin/systemctl reboot", self.text)

    def test_temporary_rtc_agent_is_local_and_removed_on_rollback(self) -> None:
        self.assertIn("RTC_UNIT=wvc-rtc-wake-m6a.service", self.text)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", self.text)
        self.assertIn("User=root", self.text)
        self.assertIn("Group=wentylacja", self.text)
        self.assertIn('sudo systemctl stop "$RTC_UNIT"', self.text)
        self.assertIn('sudo rm -f "$RTC_UNIT_PATH"', self.text)
        self.assertIn("stop_temp_rtc_best_effort", self.text)

    def test_harness_restores_main_and_keeps_lab_zero_output_gate(self) -> None:
        self.assertIn('LAB_MODE="${M6A_LAB_MODE:-0}"', self.text)
        self.assertIn('mode not in {"STOP", "FAULT"}', self.text)
        self.assertIn('sp.get("supply_voltage") != 0.0', self.text)
        self.assertIn('sp.get("extract_voltage") != 0.0', self.text)
        self.assertIn('sudo rm -f "$CORE_DROPIN"', self.text)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', self.text)
        self.assertIn('unit_cwd "$MAIN_PID_AFTER")" = "$ROOT"', self.text)
        self.assertIn("ROLLOUT_STARTED=0", self.text)

    def test_m6_alertv2_policy_is_required_during_runtime_validation(self) -> None:
        self.assertIn('--alert-policy $WT/config/alerts-v2.default.toml', self.text)
        self.assertIn('alert_v2.get("policy_version") != "2026-08-27.1"', self.text)
        self.assertIn('alert_v2.get("alert_count") != 52', self.text)
        self.assertIn('alert_v2.get("control_policy_applied") is not False', self.text)


if __name__ == "__main__":
    unittest.main()
