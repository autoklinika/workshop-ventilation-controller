from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RECHECK = REPO_ROOT / "tools" / "validate_alert_v2_stage6_lifecycle_recheck_cm5.py"


class AlertV2Stage6LifecycleRecheckTests(unittest.TestCase):
    def test_recheck_is_valid_python(self) -> None:
        ast.parse(RECHECK.read_text(encoding="utf-8"))

    def test_recheck_uses_full_core_history_window(self) -> None:
        source = RECHECK.read_text(encoding="utf-8")
        self.assertIn("ALERT_HISTORY_LIMIT = 1000", source)
        self.assertIn('client.request("alerts", limit=ALERT_HISTORY_LIMIT)', source)
        self.assertIn("_all_incident_records", source)
        self.assertNotIn("[:MAX_PERSISTENCE_IDS]", source)
        self.assertIn("IDs shifted out of the previous top-50 window were not lost", source)

    def test_recheck_is_read_only_and_never_touches_sqlite(self) -> None:
        source = RECHECK.read_text(encoding="utf-8")
        self.assertIn("CoreReadOnlyClient", source)
        self.assertIn('client.request("status")', source)
        self.assertIn('client.request("alerts"', source)
        self.assertNotIn('request("set"', source)
        self.assertNotIn('request("stop"', source)
        self.assertNotIn('request("ack-alert"', source)
        self.assertNotIn("alerts.sqlite3", source)
        self.assertIn('"control_commands_sent_by_validator": 0', source)

    def test_recheck_keeps_alertv2_control_disabled(self) -> None:
        source = RECHECK.read_text(encoding="utf-8")
        self.assertIn('"runtime_mode": "read_only_mapping"', source)
        self.assertIn('"control_policy_applied": False', source)
        self.assertIn('"reaction_execution_enabled": False', source)
        self.assertIn("require_passive_safe_state", source)

    def test_recheck_requires_real_reboot_and_same_policy(self) -> None:
        source = RECHECK.read_text(encoding="utf-8")
        self.assertIn("boot_id did not change", source)
        self.assertIn("runtime policy changed across reboot", source)
        self.assertIn('DEFAULT_POLICY = Path("/etc/workshop-ventilation/alerts-v2.toml")', source)
        self.assertIn('DEFAULT_EXPECTED_RUNTIME = Path("/home/wentylacja/wvc-alert-v2-stage4")', source)


if __name__ == "__main__":
    unittest.main()
