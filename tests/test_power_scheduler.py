from __future__ import annotations

from datetime import datetime, timezone
import unittest

from ventilation_core.application.power_scheduler import (
    RTC_WAKE_ARM_FAILED,
    PowerScheduler,
)
from ventilation_core.calendar.model import (
    CalendarMode,
    CalendarPhase,
    CalendarResolution,
)
from ventilation_core.infrastructure.rtc_wake import RtcWakeArmResult


class FakeCalendar:
    def __init__(self, resolution: CalendarResolution) -> None:
        self.resolution = resolution

    def resolve(self, now_utc=None):
        return self.resolution

    def configuration(self, now_utc=None):
        raise NotImplementedError

    def replace_configuration(self, payload):
        raise NotImplementedError

    def close(self):
        return None


class FakeRtc:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.calls: list[tuple[datetime, int]] = []

    def read_epoch(self):
        return None

    def clear(self):
        return None

    def arm(self, wake_at: datetime, *, minimum_lead_seconds: int = 60):
        self.calls.append((wake_at, minimum_lead_seconds))
        if self.fail is not None:
            raise self.fail
        epoch = int(wake_at.timestamp())
        return RtcWakeArmResult(
            requested_epoch=epoch,
            verified_epoch=epoch,
            requested_at_utc=wake_at.astimezone(timezone.utc).isoformat(),
            verified=True,
        )


def resolution(
    *,
    available: bool = True,
    phase: CalendarPhase = CalendarPhase.INACTIVE,
    mode: CalendarMode = CalendarMode.STANDBY,
    next_wake: str | None = "2026-08-31T06:30:00+02:00",
    current_period_end: str | None = None,
    last_error: str = "",
) -> CalendarResolution:
    return CalendarResolution(
        available=available,
        timezone="Europe/Warsaw",
        evaluated_at_utc="2026-08-27T10:00:00+00:00",
        local_time="2026-08-27T12:00:00+02:00",
        phase=phase,
        effective_profile="LAB_STANDBY",
        effective_mode=mode,
        rule_id="RULE",
        current_period_start=None,
        current_period_end=current_period_end,
        next_transition=next_wake,
        next_transition_reason="START_PREVENTILATION" if next_wake else None,
        next_active_period="2026-08-31T07:00:00+02:00" if next_wake else None,
        next_wake=next_wake,
        last_error=last_error,
    )


class PowerSchedulerTest(unittest.TestCase):
    NOW = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)

    def test_disabled_by_default_never_arms_rtc(self) -> None:
        rtc = FakeRtc()
        scheduler = PowerScheduler(FakeCalendar(resolution()), rtc)

        state = scheduler.prepare_scheduled_shutdown(self.NOW)

        self.assertFalse(state.scheduled_shutdown_enabled)
        self.assertFalse(state.shutdown_ready)
        self.assertEqual(state.shutdown_inhibited_reason, "scheduled_shutdown_disabled")
        self.assertEqual(rtc.calls, [])

    def test_inactive_standby_arms_verified_rtc_but_does_not_power_off(self) -> None:
        rtc = FakeRtc()
        scheduler = PowerScheduler(
            FakeCalendar(resolution()),
            rtc,
            enabled=True,
            minimum_wake_lead_seconds=120,
        )

        state = scheduler.prepare_scheduled_shutdown(self.NOW)

        self.assertTrue(state.shutdown_ready)
        self.assertTrue(state.rtc_alarm_armed)
        self.assertTrue(state.rtc_alarm_verified)
        self.assertIsNone(state.shutdown_inhibited_reason)
        self.assertEqual(state.next_wake_at_utc, "2026-08-31T04:30:00+00:00")
        self.assertEqual(len(rtc.calls), 1)
        self.assertEqual(rtc.calls[0][0], datetime(2026, 8, 31, 4, 30, tzinfo=timezone.utc))
        self.assertEqual(rtc.calls[0][1], 120)

    def test_active_calendar_never_arms_rtc(self) -> None:
        rtc = FakeRtc()
        scheduler = PowerScheduler(
            FakeCalendar(
                resolution(
                    phase=CalendarPhase.ACTIVE,
                    mode=CalendarMode.AUTO,
                    current_period_end="2026-08-27T17:30:00+02:00",
                )
            ),
            rtc,
            enabled=True,
        )

        state = scheduler.prepare_scheduled_shutdown(self.NOW)

        self.assertFalse(state.shutdown_ready)
        self.assertEqual(state.shutdown_inhibited_reason, "calendar_not_inactive")
        self.assertEqual(state.next_shutdown_at, "2026-08-27T17:30:00+02:00")
        self.assertEqual(rtc.calls, [])

    def test_calendar_unavailable_inhibits_shutdown(self) -> None:
        rtc = FakeRtc()
        scheduler = PowerScheduler(
            FakeCalendar(resolution(available=False, last_error="db unavailable")),
            rtc,
            enabled=True,
        )

        state = scheduler.prepare_scheduled_shutdown(self.NOW)

        self.assertFalse(state.shutdown_ready)
        self.assertEqual(state.shutdown_inhibited_reason, "calendar_unavailable")
        self.assertEqual(state.last_error, "db unavailable")
        self.assertEqual(rtc.calls, [])

    def test_missing_next_wake_inhibits_shutdown(self) -> None:
        rtc = FakeRtc()
        scheduler = PowerScheduler(
            FakeCalendar(resolution(next_wake=None)),
            rtc,
            enabled=True,
        )

        state = scheduler.prepare_scheduled_shutdown(self.NOW)

        self.assertFalse(state.shutdown_ready)
        self.assertEqual(state.shutdown_inhibited_reason, "next_wake_unavailable")
        self.assertEqual(rtc.calls, [])

    def test_too_close_next_wake_inhibits_before_rtc_write(self) -> None:
        rtc = FakeRtc()
        scheduler = PowerScheduler(
            FakeCalendar(resolution(next_wake="2026-08-27T12:01:00+02:00")),
            rtc,
            enabled=True,
            minimum_wake_lead_seconds=120,
        )

        state = scheduler.prepare_scheduled_shutdown(self.NOW)

        self.assertFalse(state.shutdown_ready)
        self.assertEqual(state.shutdown_inhibited_reason, "next_wake_too_close")
        self.assertEqual(rtc.calls, [])

    def test_rtc_arm_failure_sets_required_alert_and_aborts_shutdown(self) -> None:
        rtc = FakeRtc(fail=RuntimeError("read-back mismatch"))
        scheduler = PowerScheduler(
            FakeCalendar(resolution()),
            rtc,
            enabled=True,
        )

        state = scheduler.prepare_scheduled_shutdown(self.NOW)

        self.assertFalse(state.shutdown_ready)
        self.assertFalse(state.rtc_alarm_verified)
        self.assertEqual(state.shutdown_inhibited_reason, "rtc_wake_arm_failed")
        self.assertEqual(state.alert_code, RTC_WAKE_ARM_FAILED)
        self.assertIn("read-back mismatch", state.last_error)

    def test_dst_offset_is_converted_to_unambiguous_utc(self) -> None:
        rtc = FakeRtc()
        scheduler = PowerScheduler(
            FakeCalendar(resolution(next_wake="2026-10-26T06:30:00+01:00")),
            rtc,
            enabled=True,
        )

        state = scheduler.diagnostics(self.NOW)

        self.assertEqual(state.next_wake_at_local, "2026-10-26T06:30:00+01:00")
        self.assertEqual(state.next_wake_at_utc, "2026-10-26T05:30:00+00:00")
        self.assertEqual(rtc.calls, [])


if __name__ == "__main__":
    unittest.main()
