from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

from tools.validate_control_engine_stage7d_tacho_confirmation_cm5 import (
    DEFAULT_CONFIRMATION_SECONDS,
    DEFAULT_TEST_VOLTAGE,
)


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_control_engine_stage7d_tacho_confirmation_cm5.sh"
VALIDATOR = ROOT / "tools" / "validate_control_engine_stage7d_tacho_confirmation_cm5.py"
PATCHER = ROOT / "tools" / "apply_validated_control_engine_tacho_confirmation.py"


class Stage7DTachoConfirmationCm5ValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = HARNESS.read_text(encoding="utf-8")
        cls.validator = VALIDATOR.read_text(encoding="utf-8")

    def test_source_files_compile(self) -> None:
        compile(self.validator, str(VALIDATOR), "exec")
        compile(PATCHER.read_text(encoding="utf-8"), str(PATCHER), "exec")
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

        blocks = re.findall(r"<<'PY'\n(.*?)\nPY", self.harness, flags=re.DOTALL)
        self.assertGreaterEqual(len(blocks), 3)
        for index, block in enumerate(blocks, start=1):
            compile(block, f"{HARNESS}:embedded-python-{index}", "exec")

    def test_runtime_point_is_pinned_to_validated_1v_and_4s(self) -> None:
        self.assertEqual(DEFAULT_TEST_VOLTAGE, 1.0)
        self.assertEqual(DEFAULT_CONFIRMATION_SECONDS, 4.0)
        self.assertIn("--test-voltage 1.0", self.harness)
        self.assertIn("--confirmation-seconds 4.0", self.harness)
        self.assertIn("pinned to the physically characterized 1.0 V", self.validator)
        self.assertIn("pinned to the validated 4.0 s", self.validator)

    def test_harness_uses_isolated_automation_db_and_does_not_write_production_row(self) -> None:
        self.assertIn("TEST_ROOT=/var/tmp/wvc-control-engine-stage7d-validation", self.harness)
        self.assertIn("--automation-db $TEST_ROOT/automation.sqlite3", self.harness)
        self.assertNotIn("--automation-db $PRODUCTION_AUTOMATION_DB", self.harness)
        self.assertIn("mode=ro", self.harness)
        self.assertIn("PRODUCTION_CONTROL_ROW_BEFORE=\"$(read_production_control_row)\"", self.harness)
        self.assertIn('production_row_after="$(read_production_control_row)"', self.harness)
        self.assertIn('if [ "$production_row_after" != "$PRODUCTION_CONTROL_ROW_BEFORE" ]', self.harness)

    def test_validated_patcher_is_applied_only_to_isolated_runtime_and_persists_restart(self) -> None:
        self.assertIn("apply_validated_control_engine_tacho_confirmation.py", self.harness)
        self.assertIn("--confirm-apply", self.harness)
        self.assertIn('assert_tacho_config 2 "$WT/src"', self.harness)
        self.assertGreaterEqual(self.harness.count('assert_tacho_config 2 "$WT/src"'), 3)
        self.assertIn("===== 4. RESTART BRANCH CORE AND VERIFY PERSISTENCE =====", self.harness)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', self.harness)
        self.assertIn("isolated initial TACHO confirmation is not null", self.harness)

    def test_fallbacks_remain_unconfigured(self) -> None:
        for field in (
            "tacho_supply_fault_fallback_supply_pct",
            "tacho_supply_fault_fallback_extract_pct",
            "tacho_extract_fault_fallback_supply_pct",
            "tacho_extract_fault_fallback_extract_pct",
            "tacho_both_fault_fallback_supply_pct",
            "tacho_both_fault_fallback_extract_pct",
        ):
            self.assertIn(field, self.harness)
        self.assertIn("all TACHO fallbacks remain null", self.harness)
        self.assertNotIn("tacho_fallback_supply_pct =", self.validator)
        self.assertNotIn("tacho_fallback_extract_pct =", self.validator)

    def test_positive_start_requires_confirming_then_healthy_without_false_fault(self) -> None:
        for expected in (
            'status != "CONFIRMING"',
            'status == "FEEDBACK_MISSING_CONFIRMED"',
            "sample.fault_confirmed is True",
            "confirming_seen[channel] = True",
            "CONFIRMING -> HEALTHY",
            'zone.get("tacho_fault_pattern")',
            'zone.get("tacho_fallback_applied") is True',
            "first_healthy_seconds",
        ):
            self.assertIn(expected, self.validator)
        self.assertIn("healthy feedback arrived at/after configured confirmation deadline", self.validator)

    def test_physical_cleanup_and_shadow_boundary_are_mandatory(self) -> None:
        self.assertIn("finally:", self.validator)
        self.assertIn("_stop_and_verify", self.validator)
        self.assertIn('shadow.get("actuation_supported") is not False', self.harness)
        self.assertIn('shadow.get("actuation_supported") is not False', self.harness)
        self.assertIn('zone.get("proposed_supply_voltage")', self.validator)
        self.assertIn('zone.get("proposed_extract_voltage")', self.validator)
        self.assertIn("STOP / 0 V", self.harness)

    def test_host_power_rtc_shutdown_and_exact_sha_guards(self) -> None:
        for expected in (
            "EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8",
            'EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE7D_EXPECTED_BRANCH_SHA:-}"',
            "git ls-remote origin refs/heads/main",
            'git ls-remote origin "refs/heads/$BRANCH"',
            "assert_host_untouched",
            'WAKEALARM_BEFORE="$(read_wakealarm)"',
            "*--enable-scheduled-shutdown*)",
        ):
            self.assertIn(expected, self.harness)
        for forbidden in (
            "systemctl poweroff",
            "systemctl reboot",
            "/sbin/poweroff",
            "/sbin/reboot",
            'ctl "$WT/src" shutdown',
            'ctl "$ROOT/src" shutdown',
        ):
            self.assertNotIn(forbidden, self.harness)

    def test_failure_path_rolls_back_production(self) -> None:
        for expected in (
            "trap emergency_rollback EXIT INT TERM",
            'ctl "$WT/src" stop',
            'sudo rm -f "$CORE_DROPIN"',
            'sudo systemctl restart "$CORE_UNIT"',
            'git -C "$ROOT" worktree remove --force "$WT"',
            'if [ "$cwd" != "$ROOT" ]',
            'require_safe_start "$ROOT/src" "rollback production"',
        ):
            self.assertIn(expected, self.harness)


if __name__ == "__main__":
    unittest.main()
