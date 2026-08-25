from __future__ import annotations

from pathlib import Path
import unittest

from ventilation_core.hmi_power import AdbHmiPowerController, wait_for_web_state_ready


class FakeRunner:
    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, command, timeout_seconds: float) -> tuple[int, str]:
        self.calls.append((tuple(command), timeout_seconds))
        if not self.responses:
            raise AssertionError(f"unexpected command: {command!r}")
        return self.responses.pop(0)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class HmiPowerControllerTest(unittest.TestCase):
    def test_sleep_connects_and_sends_keyevent_223(self) -> None:
        runner = FakeRunner([
            (0, "connected to 192.168.1.39:5555"),
            (0, ""),
        ])
        controller = AdbHmiPowerController(
            target="192.168.1.39:5555",
            adb_path=Path("/usr/bin/adb"),
            runner=runner,
        )

        self.assertTrue(controller.sleep(strict=True))
        self.assertEqual(
            runner.calls,
            [
                (("/usr/bin/adb", "connect", "192.168.1.39:5555"), 1.5),
                (("/usr/bin/adb", "-s", "192.168.1.39:5555", "shell", "input", "keyevent", "223"), 1.5),
            ],
        )

    def test_wake_accepts_already_connected_and_sends_keyevent_224(self) -> None:
        runner = FakeRunner([
            (0, "already connected to 192.168.1.39:5555"),
            (0, ""),
        ])
        controller = AdbHmiPowerController(runner=runner)

        self.assertTrue(controller.wake(strict=True))
        self.assertEqual(runner.calls[1][0][-2:], ("keyevent", "224"))

    def test_wake_accepts_connection_after_adb_daemon_start_messages(self) -> None:
        runner = FakeRunner([
            (
                0,
                "* daemon not running; starting now at tcp:5037\n"
                "* daemon started successfully\n"
                "connected to 192.168.1.39:5555",
            ),
            (0, ""),
        ])
        controller = AdbHmiPowerController(runner=runner)

        self.assertTrue(controller.wake(strict=True))
        self.assertEqual(len(runner.calls), 2)

    def test_non_strict_failure_is_non_blocking(self) -> None:
        runner = FakeRunner([(0, "unable to connect to 192.168.1.39:5555")])
        controller = AdbHmiPowerController(runner=runner)

        self.assertFalse(controller.sleep(strict=False))

    def test_strict_failure_raises(self) -> None:
        runner = FakeRunner([(1, "connection refused")])
        controller = AdbHmiPowerController(runner=runner)

        with self.assertRaisesRegex(RuntimeError, "HMI wake unavailable"):
            controller.wake(strict=True)

    def test_retry_recovers_after_first_connect_failure(self) -> None:
        runner = FakeRunner([
            (0, "unable to connect to 192.168.1.39:5555"),
            (0, "connected to 192.168.1.39:5555"),
            (0, ""),
        ])
        sleeps: list[float] = []
        controller = AdbHmiPowerController(
            attempts=2,
            retry_delay_seconds=0.25,
            runner=runner,
            sleeper=sleeps.append,
        )

        self.assertTrue(controller.wake(strict=True))
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(len(runner.calls), 3)

    def test_web_ready_wait_polls_then_applies_watchdog_settle_window(self) -> None:
        outcomes = iter([False, False, True])
        probe_calls: list[tuple[str, float]] = []
        clock = FakeClock()

        def probe(url: str, timeout_seconds: float) -> bool:
            probe_calls.append((url, timeout_seconds))
            return next(outcomes)

        self.assertTrue(
            wait_for_web_state_ready(
                url="http://127.0.0.1:18091/api/v1/state",
                timeout_seconds=5.0,
                poll_seconds=0.5,
                request_timeout_seconds=0.25,
                settle_seconds=4.5,
                probe=probe,
                sleeper=clock.sleep,
                monotonic=clock.monotonic,
            )
        )
        self.assertEqual(len(probe_calls), 3)
        self.assertEqual(clock.sleeps, [0.5, 0.5, 4.5])

    def test_web_ready_timeout_is_best_effort_and_does_not_settle(self) -> None:
        clock = FakeClock()
        probe_calls: list[tuple[str, float]] = []

        def probe(url: str, timeout_seconds: float) -> bool:
            probe_calls.append((url, timeout_seconds))
            return False

        self.assertFalse(
            wait_for_web_state_ready(
                url="http://127.0.0.1:18091/api/v1/state",
                timeout_seconds=1.0,
                poll_seconds=0.5,
                request_timeout_seconds=0.25,
                settle_seconds=4.5,
                probe=probe,
                sleeper=clock.sleep,
                monotonic=clock.monotonic,
            )
        )
        self.assertGreaterEqual(len(probe_calls), 2)
        self.assertEqual(clock.sleeps, [0.5, 0.5])

    def test_rejects_invalid_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "host:port"):
            AdbHmiPowerController(target="192.168.1.39")


if __name__ == "__main__":
    unittest.main()
