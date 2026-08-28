from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from tools.validate_control_engine_stage7b_tacho_characterization_cm5 import _tail_stats


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_control_engine_stage7b_tacho_characterization_cm5.sh"
VALIDATOR = ROOT / "tools" / "validate_control_engine_stage7b_tacho_characterization_cm5.py"


class Stage7BTachoCharacterizationValidatorTest(unittest.TestCase):
    def test_source_files_compile(self) -> None:
        compile(VALIDATOR.read_text(encoding="utf-8"), str(VALIDATOR), "exec")
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_tail_stats_use_only_final_window(self) -> None:
        stats = _tail_stats(
            [(1.0, 100.0), (9.9, 200.0), (10.0, 300.0), (12.0, 330.0), (15.0, 360.0)],
            hold_seconds=15.0,
            tail_window=5.0,
        )
        self.assertEqual(stats["min_rpm"], 300.0)
        self.assertEqual(stats["max_rpm"], 360.0)
        self.assertAlmostEqual(stats["mean_rpm"], 330.0)
        self.assertEqual(stats["spread_rpm"], 60.0)

    def test_harness_requires_explicit_physical_confirmation_and_exact_pin(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn('CONTROL_ENGINE_STAGE7B_CONFIRM_PHYSICAL_FAN_SPIN:-', text)
        self.assertIn('[ "$CONFIRM_PHYSICAL_SPIN" = "YES" ]', text)
        self.assertIn('EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE7B_EXPECTED_BRANCH_SHA:-}"', text)
        self.assertIn("git ls-remote origin refs/heads/main", text)
        self.assertIn('git ls-remote origin "refs/heads/$BRANCH"', text)
        self.assertIn('[ "$BRANCH_LS_REMOTE" = "$EXPECTED_BRANCH_SHA" ]', text)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', text)

    def test_characterization_is_fixed_duration_three_cycle_test(self) -> None:
        harness = HARNESS.read_text(encoding="utf-8")
        validator = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("--test-voltage 2.0", harness)
        self.assertIn("--hold-seconds 15.0", harness)
        self.assertIn("--cycles 3", harness)
        self.assertIn("--tail-window 5.0", harness)
        self.assertIn("15 s x 3 cycles", harness)
        self.assertIn("if elapsed >= args.hold_seconds:", validator)
        self.assertIn("Stage7B hold-seconds must be >= 10.0", validator)
        self.assertNotIn("stable_count", validator)
        self.assertNotIn("reached_stable", validator)

    def test_validator_records_detection_and_end_of_hold_rpm(self) -> None:
        text = VALIDATOR.read_text(encoding="utf-8")
        for expected in (
            '"first_healthy_seconds"',
            '"tail_rpm"',
            '"max_first_healthy_seconds"',
            '"tail_mean_rpm_across_cycles"',
            "TRACE: cycle",
            "observed detection bound",
        ):
            self.assertIn(expected, text)

    def test_scope_stays_guarded_low_speed_and_writes_no_tuning(self) -> None:
        text = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("1.0 <= args.test_voltage <= 3.0", text)
        self.assertIn('"command": "set"', text)
        self.assertIn("_stop_and_verify", text)
        self.assertIn("finally:", text)
        self.assertIn("no Control Engine tuning value was written automatically", text)
        self.assertNotIn("control-engine-replace", text)
        self.assertNotIn("aero-speed", text)
        self.assertNotIn("aero-airing", text)

    def test_harness_preserves_host_rtc_and_rejects_scheduled_shutdown(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn("assert_host_untouched", text)
        self.assertIn('WAKEALARM_BEFORE="$(read_wakealarm)"', text)
        self.assertIn("*--enable-scheduled-shutdown*)", text)
        self.assertIn("scheduled shutdown unexpectedly enabled", text)
        for forbidden in (
            "systemctl poweroff",
            "systemctl reboot",
            "/sbin/poweroff",
            "/sbin/reboot",
            'ctl "$WT/src" shutdown',
            'ctl "$ROOT/src" shutdown',
        ):
            self.assertNotIn(forbidden, text)

    def test_cleanup_always_returns_to_zero_and_production_runtime(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn("trap emergency_rollback EXIT INT TERM", text)
        self.assertIn('ctl "$WT/src" stop', text)
        self.assertIn('sudo rm -f "$CORE_DROPIN"', text)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', text)
        self.assertIn('[ "$cwd" != "$ROOT" ]', text)
        self.assertIn('sp.get("supply_voltage") != 0.0', text)
        self.assertIn('sp.get("extract_voltage") != 0.0', text)


if __name__ == "__main__":
    unittest.main()
