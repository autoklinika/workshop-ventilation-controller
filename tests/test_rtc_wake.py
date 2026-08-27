from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from ventilation_core.infrastructure.rtc_wake import RtcWakeArmError, SysfsRtcWakeAlarm


class MismatchRtc(SysfsRtcWakeAlarm):
    def _write_raw(self, value: str) -> None:
        if value == "0":
            super()._write_raw(value)
            return
        super()._write_raw(str(int(value) + 1))


class RtcWakeAlarmTest(unittest.TestCase):
    def test_arm_absolute_epoch_and_verify_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wakealarm"
            path.write_text("\n", encoding="ascii")
            rtc = SysfsRtcWakeAlarm(
                path,
                clock=lambda: datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
            )
            target = datetime(2026, 8, 27, 12, 5, tzinfo=timezone.utc)

            result = rtc.arm(target, minimum_lead_seconds=120)

            self.assertTrue(result.verified)
            self.assertEqual(result.requested_epoch, int(target.timestamp()))
            self.assertEqual(result.verified_epoch, int(target.timestamp()))
            self.assertEqual(rtc.read_epoch(), int(target.timestamp()))

    def test_clear_accepts_kernel_empty_or_zero_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wakealarm"
            path.write_text("123\n", encoding="ascii")
            rtc = SysfsRtcWakeAlarm(path)
            rtc.clear()
            self.assertIsNone(rtc.read_epoch())

    def test_rejects_target_too_close_before_writing_alarm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wakealarm"
            path.write_text("\n", encoding="ascii")
            rtc = SysfsRtcWakeAlarm(
                path,
                clock=lambda: datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
            )
            with self.assertRaisesRegex(RtcWakeArmError, "too close"):
                rtc.arm(
                    datetime(2026, 8, 27, 12, 0, 30, tzinfo=timezone.utc),
                    minimum_lead_seconds=60,
                )
            self.assertIsNone(rtc.read_epoch())

    def test_rejects_naive_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wakealarm"
            path.write_text("\n", encoding="ascii")
            rtc = SysfsRtcWakeAlarm(path)
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                rtc.arm(datetime(2026, 8, 27, 12, 0))

    def test_readback_mismatch_fails_and_clears_alarm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wakealarm"
            path.write_text("\n", encoding="ascii")
            rtc = MismatchRtc(
                path,
                clock=lambda: datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
            )
            with self.assertRaisesRegex(RtcWakeArmError, "read-back mismatch"):
                rtc.arm(
                    datetime(2026, 8, 27, 12, 5, tzinfo=timezone.utc),
                    minimum_lead_seconds=60,
                )
            self.assertIsNone(rtc.read_epoch())


if __name__ == "__main__":
    unittest.main()
