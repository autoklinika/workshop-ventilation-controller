from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from zoneinfo import ZoneInfo

from ventilation_core.application.power_scheduler import PowerScheduler
from ventilation_core.application.power_scheduler_runtime import PowerSchedulerRuntime
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.infrastructure.rtc_wake import RtcWakeArmResult


TZ = ZoneInfo("Europe/Warsaw")


class FixedCalendar:
    def __init__(self, resolution: CalendarResolution) -> None:
        self.resolution = resolution

    def resolve(self, now_utc=None):
        return self.resolution


class FakeRtc:
    def __init__(self) -> None:
        self.value: int | None = None
        self.arm_calls = 0
        self.clear_calls = 0
        self.fail = False

    def read_epoch(self):
        return self.value

    def clear(self):
        self.clear_calls += 1
        self.value = None

    def arm(self, wake_at, *, minimum_lead_seconds=60):
        self.arm_calls += 1
        if self.fail:
            raise RuntimeError("rtc failed")
        epoch = int(wake_at.timestamp())
        self.value = epoch
        return RtcWakeArmResult(epoch, epoch, wake_at.astimezone(timezone.utc).isoformat(), True)


class FakeHostPower:
    def __init__(self) -> None:
        self.actions: list[str] = []
        self.accept = True

    def request(self, action: str):
        self.actions.append(action)
        return {"ok": self.accept, "accepted": self.accept, "action": action}


def resolution(now: datetime, wake: datetime) -> CalendarResolution:
    local_now = now.astimezone(TZ)
    local_wake = wake.astimezone(TZ)
    return CalendarResolution(
        available=True,
        timezone="Europe/Warsaw",
        evaluated_at_utc=now.isoformat(),
        local_time=local_now.isoformat(),
        phase=CalendarPhase.INACTIVE,
        effective_profile="M6_STANDBY",
        effective_mode=CalendarMode.STANDBY,
        rule_id="M6",
        current_period_start=None,
        current_period_end=None,
        next_transition=local_wake.isoformat(),
        next_transition_reason="START_PREVENTILATION",
        next_active_period=(local_wake + timedelta(minutes=30)).isoformat(),
        next_wake=local_wake.isoformat(),
    )


class PowerSchedulerRuntimeM6Test(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
        self.wake = self.now + timedelta(hours=1)

    def runtime(self, *, enabled=True):
        rtc = FakeRtc()
        host = FakeHostPower()
        scheduler = PowerScheduler(
            FixedCalendar(resolution(self.now, self.wake)),
            rtc,
            enabled=enabled,
            minimum_wake_lead_seconds=120,
        )
        runtime = PowerSchedulerRuntime(scheduler, host, poll_interval_seconds=3600)
        return runtime, rtc, host

    def test_snapshot_is_side_effect_free(self) -> None:
        runtime, rtc, host = self.runtime(enabled=True)
        try:
            first = runtime.snapshot().to_dict()
            second = runtime.snapshot().to_dict()
            self.assertEqual(first["next_wake_at_utc"], second["next_wake_at_utc"])
            self.assertEqual(rtc.arm_calls, 0)
            self.assertEqual(host.actions, [])
        finally:
            runtime.close()

    def test_disabled_runtime_never_arms_or_requests_power(self) -> None:
        runtime, rtc, host = self.runtime(enabled=False)
        try:
            snapshot = runtime.tick_once(self.now)
            self.assertFalse(snapshot.state.scheduled_shutdown_enabled)
            self.assertEqual(rtc.arm_calls, 0)
            self.assertEqual(host.actions, [])
        finally:
            runtime.close()

    def test_one_wake_timestamp_can_request_shutdown_only_once(self) -> None:
        runtime, rtc, host = self.runtime(enabled=True)
        try:
            first = runtime.tick_once(self.now)
            second = runtime.tick_once(self.now + timedelta(seconds=10))
            self.assertTrue(first.last_host_power_requested)
            self.assertTrue(first.last_host_power_accepted)
            self.assertFalse(second.last_host_power_requested)
            self.assertEqual(host.actions, ["shutdown"])
            self.assertEqual(rtc.arm_calls, 1)
            self.assertEqual(first.last_attempted_wake_at_utc, self.wake.isoformat())
        finally:
            runtime.close()

    def test_rtc_failure_is_attempted_once_and_never_reaches_host_power(self) -> None:
        runtime, rtc, host = self.runtime(enabled=True)
        rtc.fail = True
        try:
            first = runtime.tick_once(self.now)
            second = runtime.tick_once(self.now + timedelta(seconds=10))
            self.assertEqual(first.state.alert_code, "RTC_WAKE_ARM_FAILED")
            self.assertFalse(first.last_host_power_requested)
            self.assertFalse(second.last_host_power_requested)
            self.assertEqual(rtc.arm_calls, 1)
            self.assertEqual(host.actions, [])
        finally:
            runtime.close()

    def test_host_power_rejection_clears_rtc_and_is_not_retried(self) -> None:
        runtime, rtc, host = self.runtime(enabled=True)
        host.accept = False
        try:
            first = runtime.tick_once(self.now)
            runtime.tick_once(self.now + timedelta(seconds=10))
            self.assertEqual(first.state.alert_code, "HOST_POWER_REQUEST_FAILED")
            self.assertIsNone(rtc.value)
            self.assertGreaterEqual(rtc.clear_calls, 1)
            self.assertEqual(host.actions, ["shutdown"])
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()
