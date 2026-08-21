from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ventilation_core.alert_policy_runtime import RuntimeAlertPolicyManager
from ventilation_core.application.alert_v2_policy_service import AlertV2ReadOnlyPolicyService
from ventilation_core.domain.alerts import AlertRecord
from ventilation_core.domain.models import (
    AlarmCode,
    AlarmSeverity,
    AlarmState,
    CoreState,
    FanSetpoints,
    VentilationMode,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPO_ROOT / "config" / "alerts-v2.default.toml"


class _FakeService:
    def __init__(self, *, acknowledged: bool = False) -> None:
        ack = "2026-08-18T20:00:00+00:00" if acknowledged else None
        self._alarm = AlarmState(
            code=AlarmCode.AERO_BUS_UNAVAILABLE,
            severity=AlarmSeverity.WARNING,
            message="legacy AERO warning",
            active_since="2026-08-18T19:00:00+00:00",
            last_error="timeout",
            occurrences=3,
            alert_id=7,
            source="aero",
            acknowledged_at=ack,
        )
        self._record = AlertRecord(
            alert_id=7,
            key="aero:bus",
            code=AlarmCode.AERO_BUS_UNAVAILABLE,
            source="aero",
            severity=AlarmSeverity.WARNING,
            message="legacy AERO warning",
            detail="timeout",
            active_since="2026-08-18T19:00:00+00:00",
            acknowledged_at=ack,
            cleared_at=None,
            occurrences=3,
        )
        self.control_calls: list[tuple[float, float]] = []

    def state(self) -> CoreState:
        return CoreState(
            mode=VentilationMode.MANUAL,
            setpoints=FanSetpoints(2.0, 2.0),
            hardware_ready=True,
            active_alarms=(self._alarm,),
        )

    def active_alerts(self) -> tuple[AlertRecord, ...]:
        return (self._record,)

    def alert_history(self, limit: int = 200) -> tuple[AlertRecord, ...]:
        return (self._record,)[:limit]

    def acknowledge_alert(self, alert_id: int) -> AlertRecord:
        if alert_id != 7:
            raise ValueError("unknown alert")
        return self._record

    def set_manual(self, supply_voltage: float, extract_voltage: float) -> str:
        self.control_calls.append((supply_voltage, extract_voltage))
        return "delegated-control-result"


class AlertV2RuntimePolicyTests(unittest.TestCase):
    def _runtime_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "alerts-v2.toml"
        path.write_bytes(DEFAULT_POLICY.read_bytes())
        return directory, path

    def test_valid_policy_loads_read_only_with_version_and_sha(self) -> None:
        manager = RuntimeAlertPolicyManager(DEFAULT_POLICY)
        metadata = manager.metadata()
        self.assertTrue(metadata["loaded"])
        self.assertEqual(metadata["runtime_mode"], "read_only_mapping")
        self.assertEqual(metadata["policy_version"], "2026-08-21.1")
        self.assertEqual(metadata["alert_count"], 50)
        self.assertEqual(len(metadata["sha256"]), 64)
        self.assertFalse(metadata["control_policy_applied"])
        self.assertIsNone(metadata["last_error"])

    def test_invalid_reload_keeps_last_known_good_policy(self) -> None:
        directory, path = self._runtime_copy()
        self.addCleanup(directory.cleanup)
        manager = RuntimeAlertPolicyManager(path)
        original = manager.metadata()
        self.assertTrue(original["loaded"])

        path.write_text("schema_version = [", encoding="utf-8")
        self.assertFalse(manager.reload())

        after = manager.metadata()
        self.assertTrue(after["loaded"])
        self.assertEqual(after["policy_version"], original["policy_version"])
        self.assertEqual(after["sha256"], original["sha256"])
        self.assertIsNotNone(after["last_error"])
        self.assertIn("cannot parse TOML policy", after["last_error"])

    def test_missing_initial_policy_is_nonfatal_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.toml"
            manager = RuntimeAlertPolicyManager(path)
            metadata = manager.metadata()
        self.assertFalse(metadata["loaded"])
        self.assertIsNone(metadata["policy_version"])
        self.assertIsNone(metadata["sha256"])
        self.assertFalse(metadata["control_policy_applied"])
        self.assertIn("cannot read policy", metadata["last_error"])

    def test_existing_stage1_alert_is_enriched_without_overwriting_legacy_fields(self) -> None:
        manager = RuntimeAlertPolicyManager(DEFAULT_POLICY)
        delegate = _FakeService()
        service = AlertV2ReadOnlyPolicyService(delegate, manager)

        payload = service.active_alerts()[0].to_dict()
        self.assertEqual(payload["severity"], "warning")
        self.assertEqual(payload["message"], "legacy AERO warning")
        self.assertTrue(payload["alert_v2"]["mapped"])
        self.assertEqual(payload["alert_v2"]["weight"], 4)
        self.assertEqual(payload["alert_v2"]["severity"], "critical")
        self.assertEqual(payload["alert_v2"]["reaction"], "fallback_local")
        self.assertEqual(payload["alert_v2"]["hmi_color"], "red")
        self.assertTrue(payload["alert_v2"]["affects_control"])

    def test_state_publishes_policy_sha_and_highest_active_weight(self) -> None:
        manager = RuntimeAlertPolicyManager(DEFAULT_POLICY)
        service = AlertV2ReadOnlyPolicyService(_FakeService(), manager)

        state = service.state().to_dict()
        self.assertEqual(state["alert_v2"]["policy_version"], "2026-08-21.1")
        self.assertEqual(len(state["alert_v2"]["sha256"]), 64)
        self.assertEqual(state["alert_v2"]["active_weight"], 4)
        self.assertEqual(state["alert_v2"]["hmi_color"], "red")
        self.assertEqual(state["alert_v2"]["mapped_active_alerts"], 1)
        self.assertEqual(state["alert_v2"]["unmapped_active_alerts"], 0)
        self.assertFalse(state["alert_v2"]["control_policy_applied"])
        self.assertEqual(state["active_alarms"][0]["alert_v2"]["weight"], 4)

    def test_ack_does_not_reduce_weight_or_hmi_color(self) -> None:
        manager = RuntimeAlertPolicyManager(DEFAULT_POLICY)
        service = AlertV2ReadOnlyPolicyService(_FakeService(acknowledged=True), manager)

        state = service.state().to_dict()
        self.assertTrue(state["active_alarms"][0]["acknowledged"])
        self.assertEqual(state["alert_v2"]["active_weight"], 4)
        self.assertEqual(state["alert_v2"]["hmi_color"], "red")

    def test_wrapper_delegates_control_unchanged_and_never_executes_reaction(self) -> None:
        manager = RuntimeAlertPolicyManager(DEFAULT_POLICY)
        delegate = _FakeService()
        service = AlertV2ReadOnlyPolicyService(delegate, manager)

        result = service.set_manual(3.0, 4.0)
        self.assertEqual(result, "delegated-control-result")
        self.assertEqual(delegate.control_calls, [(3.0, 4.0)])
        self.assertFalse(manager.metadata()["control_policy_applied"])


if __name__ == "__main__":
    unittest.main()
