from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from ventilation_core.application.control_engine_scenario import ControlEngineScenarioRunner
from ventilation_core.domain.tacho import FanTachoState, TachoMonitorState
from ventilation_core.domain.tacho_supervision import TachoFeedbackStatus, TachoSupervisionTracker


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "config" / "control-engine-scenarios" / "tacho-supervision-v1.json"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def channel(*, valid: bool, rpm: float = 0.0, line: str = "GPIO17") -> FanTachoState:
    return FanTachoState(
        line_name=line,
        line_offset=17 if line == "GPIO17" else 27,
        frequency_hz=rpm / 20.0,
        rpm=rpm,
        sample_count=6 if valid else 0,
        age_seconds=0.01 if valid else 1.0,
        valid=valid,
    )


def monitor(*, supply: FanTachoState | None, extract: FanTachoState | None, ready: bool = True) -> TachoMonitorState:
    return TachoMonitorState(
        chip_path="synthetic",
        ready=ready,
        worker_alive=ready,
        last_error=None if ready else "synthetic monitor fault",
        supply=supply,
        extract=extract,
    )


class TachoSupervisionTrackerTest(unittest.TestCase):
    def test_zero_volts_never_require_feedback_even_without_monitor(self) -> None:
        clock = Clock()
        tracker = TachoSupervisionTracker(clock=clock)
        supply, extract = tracker.evaluate(
            monitor=None,
            supply_voltage=0.0,
            extract_voltage=0.0,
            confirmation_seconds=5.0,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.NOT_REQUIRED)
        self.assertEqual(extract.status, TachoFeedbackStatus.NOT_REQUIRED)
        self.assertFalse(supply.feedback_required)
        self.assertFalse(extract.feedback_required)
        self.assertFalse(supply.fault_confirmed)
        self.assertFalse(extract.fault_confirmed)

    def test_missing_feedback_is_confirmed_only_after_configured_interval(self) -> None:
        clock = Clock()
        tracker = TachoSupervisionTracker(clock=clock)
        state = monitor(
            supply=channel(valid=False),
            extract=channel(valid=True, rpm=430.0, line="GPIO27"),
        )

        supply, _ = tracker.evaluate(
            monitor=state,
            supply_voltage=2.0,
            extract_voltage=2.0,
            confirmation_seconds=5.0,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.CONFIRMING)
        self.assertFalse(supply.fault_confirmed)

        clock.now += timedelta(seconds=4.9)
        supply, _ = tracker.evaluate(
            monitor=state,
            supply_voltage=2.0,
            extract_voltage=2.0,
            confirmation_seconds=5.0,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.CONFIRMING)

        clock.now += timedelta(seconds=0.1)
        supply, _ = tracker.evaluate(
            monitor=state,
            supply_voltage=2.0,
            extract_voltage=2.0,
            confirmation_seconds=5.0,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.FEEDBACK_MISSING_CONFIRMED)
        self.assertTrue(supply.fault_confirmed)

    def test_recovery_or_stop_resets_pending_failure_state(self) -> None:
        clock = Clock()
        tracker = TachoSupervisionTracker(clock=clock)
        missing = monitor(
            supply=channel(valid=False),
            extract=channel(valid=True, rpm=430.0, line="GPIO27"),
        )
        healthy = monitor(
            supply=channel(valid=True, rpm=420.0),
            extract=channel(valid=True, rpm=430.0, line="GPIO27"),
        )

        tracker.evaluate(
            monitor=missing,
            supply_voltage=2.0,
            extract_voltage=0.0,
            confirmation_seconds=5.0,
        )
        clock.now += timedelta(seconds=5)
        supply, _ = tracker.evaluate(
            monitor=missing,
            supply_voltage=2.0,
            extract_voltage=0.0,
            confirmation_seconds=5.0,
        )
        self.assertTrue(supply.fault_confirmed)

        supply, _ = tracker.evaluate(
            monitor=healthy,
            supply_voltage=2.0,
            extract_voltage=0.0,
            confirmation_seconds=5.0,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.HEALTHY)
        self.assertFalse(supply.fault_confirmed)
        self.assertIsNone(supply.pending_since_utc)

        supply, _ = tracker.evaluate(
            monitor=None,
            supply_voltage=0.0,
            extract_voltage=0.0,
            confirmation_seconds=5.0,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.NOT_REQUIRED)
        self.assertIsNone(supply.pending_since_utc)

    def test_missing_confirmation_tuning_is_explicit_and_not_a_confirmed_fault(self) -> None:
        clock = Clock()
        tracker = TachoSupervisionTracker(clock=clock)
        state = monitor(
            supply=channel(valid=False),
            extract=channel(valid=True, rpm=430.0, line="GPIO27"),
        )
        supply, _ = tracker.evaluate(
            monitor=state,
            supply_voltage=2.0,
            extract_voltage=0.0,
            confirmation_seconds=None,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.CONFIRMATION_TUNING_REQUIRED)
        self.assertFalse(supply.fault_confirmed)
        self.assertIsNone(supply.pending_since_utc)

    def test_monitor_or_channel_unavailable_is_immediate_when_commanded_on(self) -> None:
        clock = Clock()
        tracker = TachoSupervisionTracker(clock=clock)

        supply, _ = tracker.evaluate(
            monitor=None,
            supply_voltage=2.0,
            extract_voltage=0.0,
            confirmation_seconds=5.0,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.MONITOR_UNAVAILABLE)
        self.assertTrue(supply.fault_confirmed)

        supply, _ = tracker.evaluate(
            monitor=monitor(supply=None, extract=channel(valid=False, line="GPIO27")),
            supply_voltage=2.0,
            extract_voltage=0.0,
            confirmation_seconds=5.0,
        )
        self.assertEqual(supply.status, TachoFeedbackStatus.CHANNEL_UNAVAILABLE)
        self.assertTrue(supply.fault_confirmed)


class TachoScenarioTest(unittest.TestCase):
    def test_versioned_start_fault_partial_recovery_full_recovery_sequence(self) -> None:
        payload = json.loads(SCENARIO.read_text(encoding="utf-8"))
        result = ControlEngineScenarioRunner().run(payload).to_dict()
        self.assertFalse(result["actuation_supported"])
        self.assertEqual(result["policy_version"], "scenario-tacho-supervision-v1")
        self.assertEqual(len(result["steps"]), 7)

        def zone(index: int) -> dict:
            return next(
                item
                for item in result["steps"][index]["shadow"]["zones"]
                if item["zone"] == "zone-1"
            )

        stopped = zone(0)
        self.assertEqual(stopped["tacho_supply_status"], "NOT_REQUIRED")
        self.assertEqual(stopped["tacho_extract_status"], "NOT_REQUIRED")
        self.assertIsNotNone(stopped["final_supply_pct"])
        self.assertIsNotNone(stopped["final_extract_pct"])

        spinup = zone(1)
        self.assertEqual(spinup["tacho_supply_status"], "CONFIRMING")
        self.assertEqual(spinup["tacho_extract_status"], "CONFIRMING")
        self.assertFalse(spinup["tacho_supply_fault_confirmed"])
        self.assertFalse(spinup["tacho_extract_fault_confirmed"])

        before_deadline = zone(2)
        self.assertEqual(before_deadline["tacho_supply_status"], "CONFIRMING")
        self.assertEqual(before_deadline["tacho_extract_status"], "CONFIRMING")

        fault = zone(3)
        self.assertEqual(fault["tacho_supply_status"], "FEEDBACK_MISSING_CONFIRMED")
        self.assertEqual(fault["tacho_extract_status"], "FEEDBACK_MISSING_CONFIRMED")
        self.assertEqual(fault["automation_state"], "FAULT")
        self.assertIsNone(fault["final_supply_pct"])
        self.assertIsNone(fault["final_extract_pct"])
        self.assertEqual(
            fault["control_reason"],
            "TACHO_FEEDBACK_FAULT:EMERGENCY_POLICY_REQUIRED",
        )

        partial = zone(4)
        self.assertEqual(partial["tacho_supply_status"], "HEALTHY")
        self.assertEqual(partial["tacho_extract_status"], "FEEDBACK_MISSING_CONFIRMED")
        self.assertEqual(partial["automation_state"], "FAULT")
        self.assertIsNone(partial["final_supply_pct"])
        self.assertIsNone(partial["final_extract_pct"])

        recovered = zone(5)
        self.assertEqual(recovered["tacho_supply_status"], "HEALTHY")
        self.assertEqual(recovered["tacho_extract_status"], "HEALTHY")
        self.assertFalse(recovered["tacho_supply_fault_confirmed"])
        self.assertFalse(recovered["tacho_extract_fault_confirmed"])
        self.assertIsNotNone(recovered["final_supply_pct"])
        self.assertIsNotNone(recovered["final_extract_pct"])

        stopped_again = zone(6)
        self.assertEqual(stopped_again["tacho_supply_status"], "NOT_REQUIRED")
        self.assertEqual(stopped_again["tacho_extract_status"], "NOT_REQUIRED")
        self.assertFalse(stopped_again["tacho_supply_fault_confirmed"])
        self.assertFalse(stopped_again["tacho_extract_fault_confirmed"])

        for step in result["steps"]:
            self.assertFalse(step["shadow"]["actuation_supported"])
            for item in step["shadow"]["zones"]:
                self.assertIsNone(item["proposed_supply_voltage"])
                self.assertIsNone(item["proposed_extract_voltage"])


if __name__ == "__main__":
    unittest.main()
