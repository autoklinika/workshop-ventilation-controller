from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "deploy_web_gui_automation_stage3_branch_runtime_cm5.sh"


class Stage3BranchRuntimeDeploymentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_script_has_valid_bash_syntax(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        subprocess.run([bash, "-n", str(SCRIPT)], check=True)

    def test_runtime_is_pinned_to_physically_validated_stage3_sha(self):
        self.assertIn(
            "RUNTIME_SHA=7d29c09a842a2888294a57d1611ea1f0609f4a39",
            self.source,
        )
        self.assertIn(
            "EXPECTED_MAIN=7628c407cfc9c0ea72d262566759ea2d4598fec8",
            self.source,
        )
        self.assertIn("BRANCH=agent/web-gui-automation-stage3-deployment", self.source)
        self.assertIn('git -C "$ROOT" merge-base --is-ancestor "$RUNTIME_SHA"', self.source)

    def test_deployment_never_merges_or_changes_main_checkout(self):
        forbidden = (
            "git merge ",
            "git rebase ",
            "git cherry-pick ",
            'git -C "$ROOT" checkout',
            'git -C "$ROOT" switch',
            'git -C "$ROOT" reset',
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.source)
        self.assertIn('git -C "$ROOT" worktree add --detach "$WT" "$RUNTIME_SHA"', self.source)
        self.assertIn('production checkout must remain on main', self.source)
        self.assertIn('production main checkout is dirty', self.source)

    def test_only_systemd_runtime_path_is_redirected_to_branch(self):
        self.assertIn("WorkingDirectory=$WT", self.source)
        self.assertIn("Environment=PYTHONPATH=$WT/src", self.source)
        self.assertIn("90-webgui-automation-stage3-branch-runtime.conf", self.source)
        self.assertNotIn("ExecStart=", self.source)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', self.source)
        self.assertIn('sudo systemctl restart "$WEB_UNIT"', self.source)

    def test_apply_requires_safe_zero_state_and_shadow_after_restart(self):
        self.assertIn('require_zero_and_shadow "$ROOT/src" "pre-deploy production" 0', self.source)
        self.assertIn('require_zero_and_shadow "$WT/src" "Stage3 branch core" 1', self.source)
        self.assertIn('require_zero_and_shadow "$WT/src" "post-deploy Stage3 runtime" 1', self.source)
        self.assertIn('shadow.get("actuation_supported") is not False', self.source)
        self.assertIn('readiness.get("actuation_authorized") is not False', self.source)
        self.assertIn('readiness.get("ready") is not False', self.source)

    def test_deployment_has_no_physical_control_or_host_power_action(self):
        forbidden = (
            "ctl set",
            "ctl stop",
            "aero-speed",
            "aero-airing",
            "systemctl poweroff",
            "systemctl reboot",
            "/sbin/shutdown",
            "/sbin/reboot",
            '"action":"shutdown"',
            '"action":"restart"',
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.source)

    def test_webgui_is_required_on_port_18091_with_automation_route(self):
        self.assertIn("WEB_URL=http://127.0.0.1:18091", self.source)
        self.assertIn('"$WEB_URL/automation"', self.source)
        self.assertIn('"$WEB_URL/api/v1/state"', self.source)
        self.assertIn('current production WebGUI port is $web_port_before, expected 18091', self.source)
        self.assertIn('Stage3 WebGUI effective port=$web_port expected=18091', self.source)

    def test_apply_preserves_host_rtc_and_boot(self):
        self.assertIn("boot_before=", self.source)
        self.assertIn("host_pid_before=", self.source)
        self.assertIn("host_status_before=", self.source)
        self.assertIn("wake_before=", self.source)
        self.assertIn('boot_id changed during deployment', self.source)
        self.assertIn('host-power PID changed during deployment', self.source)
        self.assertIn('RTC wakealarm changed during deployment', self.source)

    def test_automation_db_gets_non_destructive_predeploy_backup(self):
        self.assertIn("backup_automation_db", self.source)
        self.assertIn("source.backup(target)", self.source)
        self.assertNotIn("DELETE FROM", self.source)
        self.assertNotIn("DROP TABLE", self.source)

    def test_failure_path_and_manual_rollback_restore_main_services(self):
        self.assertIn("trap emergency_restore_main ERR", self.source)
        self.assertIn("remove_dropins", self.source)
        self.assertIn('assert_main_unit "$CORE_UNIT" "ventilation-core"', self.source)
        self.assertIn('assert_main_unit "$WEB_UNIT" "wvc-web-ui"', self.source)
        self.assertIn('require_zero_and_shadow "$ROOT/src" "rollback production main" 0', self.source)
        self.assertIn('case "${1:-status}" in', self.source)
        self.assertIn("apply)", self.source)
        self.assertIn("status)", self.source)
        self.assertIn("rollback)", self.source)


if __name__ == "__main__":
    unittest.main()
