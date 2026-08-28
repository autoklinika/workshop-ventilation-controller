from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_control_engine_stage8a_readiness_cm5.sh"


class Stage8AReadinessHarnessTest(unittest.TestCase):
    def test_harness_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_harness_is_exact_sha_and_isolated_db(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn('CONTROL_ENGINE_STAGE8A_EXPECTED_BRANCH_SHA:-', text)
        self.assertIn('git ls-remote origin "refs/heads/$BRANCH"', text)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', text)
        self.assertIn('--automation-db $TEST_ROOT/automation.sqlite3', text)
        self.assertIn('production Control Engine SQLite row unchanged by isolated Stage8A', text)

    def test_harness_never_commands_fan_motion_or_host_power(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        for forbidden in (
            '"command": "set"',
            'ctl "$WT/src" set',
            'aero-speed',
            'aero-airing',
            'systemctl poweroff',
            'systemctl reboot',
            '/sbin/poweroff',
            '/sbin/reboot',
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn('EC outputs are not 0 V', text)
        self.assertIn('actuation_supported', text)

    def test_readiness_contract_requires_expected_blockers(self) -> None:
        text = HARNESS.read_text(encoding="utf-8")
        for blocker in (
            'FAN_OUTPUT_TUNING_INCOMPLETE',
            'AERO_OUTPUT_TUNING_INCOMPLETE',
            'DYNAMICS_TUNING_INCOMPLETE',
            'FAN_SENSOR_FALLBACK_UNCONFIGURED',
            'AERO_SENSOR_FALLBACK_UNCONFIGURED',
            'TACHO_SUPPLY_FALLBACK_UNCONFIGURED',
            'TACHO_EXTRACT_FALLBACK_UNCONFIGURED',
            'TACHO_BOTH_FALLBACK_UNCONFIGURED',
            'ACTUATION_AUTHORITY_NOT_IMPLEMENTED',
        ):
            self.assertIn(blocker, text)
        self.assertIn('"TACHO_CONFIRMATION_UNCONFIGURED" in blockers', text)
        self.assertIn('readiness.get("ready") is not False', text)
        self.assertIn('readiness.get("actuation_authorized") is not False', text)


if __name__ == "__main__":
    unittest.main()
