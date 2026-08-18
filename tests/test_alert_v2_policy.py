from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ventilation_core.alert_policy import AlertPolicyError, load_alert_policy
from ventilation_core.alertctl import main as alertctl_main


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPO_ROOT / "config" / "alerts-v2.default.toml"


def _mutate_alert(text: str, code: str, old: str, new: str) -> str:
    marker = f"[alerts.{code}]"
    start = text.index(marker)
    next_table = text.find("\n[alerts.", start + len(marker))
    if next_table < 0:
        next_table = len(text)
    section = text[start:next_table]
    if old not in section:
        raise AssertionError(f"{old!r} not found in {code}")
    section = section.replace(old, new, 1)
    return text[:start] + section + text[next_table:]


class AlertV2PolicyTests(unittest.TestCase):
    def _write_policy(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "alerts-v2.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_default_policy_loads_and_has_expected_contract(self) -> None:
        policy = load_alert_policy(DEFAULT_POLICY)
        self.assertEqual(policy.schema_version, 1)
        self.assertEqual(policy.policy_version, "2026-08-18.1")
        self.assertEqual(policy.alert_count, 49)
        self.assertEqual(len(policy.sha256), 64)

        tacho = policy.get("TACHO_MONITOR_UNAVAILABLE")
        self.assertIsNotNone(tacho)
        assert tacho is not None
        self.assertEqual(tacho.weight, 2)
        self.assertEqual(tacho.reaction, "continue_degraded")
        self.assertFalse(tacho.affects_control)
        self.assertEqual(tacho.hmi_color, "yellow")

        dac = policy.get("DAC_COMMUNICATION_LOST")
        self.assertIsNotNone(dac)
        assert dac is not None
        self.assertEqual(dac.weight, 4)
        self.assertEqual(dac.reaction, "safe_state")
        self.assertTrue(dac.affects_control)
        self.assertEqual(dac.hmi_color, "red")

    def test_tacho_policy_cannot_be_changed_to_safe_state(self) -> None:
        text = DEFAULT_POLICY.read_text(encoding="utf-8")
        text = _mutate_alert(
            text,
            "TACHO_MONITOR_UNAVAILABLE",
            'reaction = "continue_degraded"',
            'reaction = "safe_state"',
        )
        with self.assertRaises(AlertPolicyError) as ctx:
            load_alert_policy(self._write_policy(text))
        self.assertIn("loss of TACHO never stops ventilation", str(ctx.exception))

    def test_tacho_policy_cannot_affect_control(self) -> None:
        text = DEFAULT_POLICY.read_text(encoding="utf-8")
        text = _mutate_alert(
            text,
            "TACHO_CONFIGURATION_INVALID",
            "affects_control = false",
            "affects_control = true",
        )
        with self.assertRaises(AlertPolicyError) as ctx:
            load_alert_policy(self._write_policy(text))
        self.assertIn("loss of TACHO is diagnostic only", str(ctx.exception))

    def test_dac_communication_lost_cannot_be_downgraded_to_continue(self) -> None:
        text = DEFAULT_POLICY.read_text(encoding="utf-8")
        text = _mutate_alert(
            text,
            "DAC_COMMUNICATION_LOST",
            'reaction = "safe_state"',
            'reaction = "continue"',
        )
        with self.assertRaises(AlertPolicyError) as ctx:
            load_alert_policy(self._write_policy(text))
        self.assertIn("DAC_COMMUNICATION_LOST.reaction must remain 'safe_state'", str(ctx.exception))

    def test_weight_severity_and_hmi_color_must_match(self) -> None:
        text = DEFAULT_POLICY.read_text(encoding="utf-8")
        text = _mutate_alert(
            text,
            "AI_ADVISORY_UNAVAILABLE",
            'hmi_color = "blue"',
            'hmi_color = "red"',
        )
        with self.assertRaises(AlertPolicyError) as ctx:
            load_alert_policy(self._write_policy(text))
        self.assertIn("hmi_color must be 'blue' for weight 1", str(ctx.exception))

    def test_non_control_domain_cannot_gain_control_authority(self) -> None:
        text = DEFAULT_POLICY.read_text(encoding="utf-8")
        text = _mutate_alert(
            text,
            "WEATHER_UNAVAILABLE",
            "affects_control = false",
            "affects_control = true",
        )
        with self.assertRaises(AlertPolicyError) as ctx:
            load_alert_policy(self._write_policy(text))
        self.assertIn("WEATHER_UNAVAILABLE.affects_control must remain false", str(ctx.exception))

    def test_detector_parameters_subtable_is_allowed(self) -> None:
        text = DEFAULT_POLICY.read_text(encoding="utf-8")
        marker = '[alerts.FAN_NO_ROTATION_FEEDBACK]\n'
        parameters = (
            '[alerts.FAN_NO_ROTATION_FEEDBACK.parameters]\n'
            'note = "progi do walidacji sprzętowej"\n\n'
        )
        start = text.index(marker)
        next_table = text.find("\n[alerts.", start + len(marker))
        self.assertGreater(next_table, 0)
        text = text[:next_table] + "\n" + parameters + text[next_table:]
        policy = load_alert_policy(self._write_policy(text))
        entry = policy.get("FAN_NO_ROTATION_FEEDBACK")
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.parameters["note"], "progi do walidacji sprzętowej")

    def test_unknown_direct_alert_field_is_rejected(self) -> None:
        text = DEFAULT_POLICY.read_text(encoding="utf-8")
        text = _mutate_alert(
            text,
            "AI_ADVISORY_UNAVAILABLE",
            'message = "Warstwa rekomendacji AI jest niedostępna. Nie ma to wpływu na lokalne sterowanie CM5."',
            'message = "Warstwa rekomendacji AI jest niedostępna. Nie ma to wpływu na lokalne sterowanie CM5."\ntypo_field = 1',
        )
        with self.assertRaises(AlertPolicyError) as ctx:
            load_alert_policy(self._write_policy(text))
        self.assertIn("has unknown fields: typo_field", str(ctx.exception))

    def test_malformed_toml_is_rejected(self) -> None:
        path = self._write_policy("schema_version = [")
        with self.assertRaises(AlertPolicyError) as ctx:
            load_alert_policy(path)
        self.assertIn("cannot parse TOML policy", str(ctx.exception))

    def test_cli_validate_human_output(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = alertctl_main(["validate", str(DEFAULT_POLICY)])
        self.assertEqual(result, 0)
        self.assertIn("PASS: AlertV2 policy valid", stdout.getvalue())
        self.assertIn("alerts=49", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_validate_json_output_and_invalid_exit_code(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = alertctl_main(["validate", "--json", str(DEFAULT_POLICY)])
        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["alerts"], 49)

        invalid = self._write_policy("schema_version = 1")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = alertctl_main(["validate", str(invalid)])
        self.assertEqual(result, 2)
        self.assertIn("INVALID:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
