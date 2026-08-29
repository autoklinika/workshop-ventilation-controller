from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from ventilation_core.domain.tuning_validation import TUNING_GROUP_REQUIREMENTS


ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "docs" / "commissioning" / "WORKSHOP_COMMISSIONING_MASTER_PLAN_PL.md"
CHECKLIST = ROOT / "docs" / "commissioning" / "WORKSHOP_COMMISSIONING_FIELD_CHECKLIST_PL.md"
SESSION = ROOT / "config" / "control-engine-workshop-commissioning-session-template-v1.json"
CANDIDATE = ROOT / "config" / "control-engine-commissioning-candidate-template-v1.json"
SNAPSHOT = ROOT / "tools" / "workshop_commissioning_snapshot.py"


class WorkshopCommissioningPackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = MASTER.read_text(encoding="utf-8")
        cls.checklist = CHECKLIST.read_text(encoding="utf-8")
        cls.session = json.loads(SESSION.read_text(encoding="utf-8"))
        cls.candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
        cls.snapshot_source = SNAPSHOT.read_text(encoding="utf-8")

    def test_documents_cover_every_authoritative_tuning_group(self):
        groups = set(TUNING_GROUP_REQUIREMENTS)
        self.assertEqual(set(self.session["groups"]), groups)
        for group in groups:
            with self.subTest(group=group):
                self.assertIn(f"`{group}`", self.master)
                self.assertIn(f"`{group}`", self.checklist)

    def test_session_candidate_value_keys_match_authoritative_candidate_template(self):
        self.assertEqual(set(self.session["groups"]), set(self.candidate["groups"]))
        for group, candidate_entry in self.candidate["groups"].items():
            with self.subTest(group=group):
                session_keys = set(self.session["groups"][group]["candidate_values"])
                candidate_keys = set(candidate_entry["values"])
                self.assertEqual(session_keys, candidate_keys)

    def test_session_is_fail_closed_and_not_runtime_bound(self):
        runtime = self.session["runtime"]
        self.assertIs(runtime["actuation_supported"], False)
        self.assertIs(runtime["actuation_authorized"], False)
        self.assertIs(runtime["readiness"], False)
        self.assertIs(runtime["default_runtime_binding"], False)
        final = self.session["final_decision"]
        self.assertIs(final["runtime_binding_requested"], False)
        self.assertIs(final["physical_authority_requested"], False)

    def test_tacho_confirmation_retains_physically_validated_4_seconds(self):
        tacho = self.session["groups"]["tacho_confirmation"]
        self.assertEqual(tacho["target_level"], "PHYSICAL_VALIDATED")
        self.assertEqual(tacho["candidate_values"]["tacho_failure_confirmation_seconds"], 4.0)
        self.assertTrue(tacho["pass"])
        self.assertIn("1/9", self.master)
        self.assertIn("4.0 s", self.master)
        self.assertIn("4.0 s", self.checklist)

    def test_workshop_validated_groups_match_domain_requirements(self):
        for group, required in TUNING_GROUP_REQUIREMENTS.items():
            expected = required.name
            self.assertEqual(self.session["groups"][group]["target_level"], expected)

    def test_master_requires_passive_baseline_and_seasonal_review(self):
        self.assertIn("48–72", self.master)
        self.assertIn("Pierwszy tydzień", self.master)
        self.assertIn("Sezonowo", self.master)
        self.assertIn("pierwsza realna zima", self.master)

    def test_master_forbids_automatic_actuation_and_rs485_hot_unplug(self):
        self.assertIn("narzędzia commissioningowe są read-only względem sterowania", self.master)
        self.assertIn("Nigdy nie wykonujemy hot-unplug RS-485", self.master)
        self.assertIn("AI może analizować dane, ale nie może wysyłać poleceń wykonawczych", self.master)
        self.assertIn("Control Engine pozostaje SHADOW", self.master)

    def test_snapshot_tool_is_valid_python(self):
        ast.parse(self.snapshot_source)

    def test_snapshot_tool_uses_get_only_and_no_control_or_restart_commands(self):
        self.assertIn('method="GET"', self.snapshot_source)
        forbidden = (
            'method="POST"',
            "ctl set",
            "ctl stop",
            "aero-speed",
            "aero-airing",
            "systemctl restart",
            "systemctl stop",
            "systemctl start",
            "systemctl poweroff",
            "systemctl reboot",
            "shutdown",
            '"action":"shutdown"',
            '"action":"restart"',
            "sudo",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.snapshot_source)

    def test_snapshot_collects_required_read_only_views(self):
        required = (
            "/api/v1/state",
            "/api/v1/control-engine",
            "/api/v1/automation/operator",
            "/api/v1/automation/tuning-validation",
            "/api/v1/calendar",
        )
        for endpoint in required:
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, self.snapshot_source)
        self.assertIn("ventilation-core.service", self.snapshot_source)
        self.assertIn("wvc-web-ui.service", self.snapshot_source)
        self.assertIn("wvc-host-power.service", self.snapshot_source)
        self.assertIn("/proc/sys/kernel/random/boot_id", self.snapshot_source)

    def test_snapshot_safe_preflight_is_strictly_shadow_zero_and_unbound(self):
        required_markers = (
            "SUPPLY_SETPOINT_NOT_ZERO",
            "EXTRACT_SETPOINT_NOT_ZERO",
            "ACTUATION_SUPPORTED_NOT_FALSE",
            "ACTUATION_AUTHORIZED_NOT_FALSE",
            "READINESS_NOT_FALSE",
            "OPERATOR_NOT_AUTO",
            "TUNING_GROUP_COUNT_NOT_9",
            "TUNING_RUNTIME_BOUND",
            "TACHO_CONFIRMATION_NOT_VALIDATED_4S",
        )
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.snapshot_source)


if __name__ == "__main__":
    unittest.main()
