from __future__ import annotations

from pathlib import Path
import unittest

from ventilation_core.hmi_power import AdbHmiPowerController


class FakeRunner:
    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, command, timeout_seconds: float) -> tuple[int, str]:
        self.calls.append((tuple(command), timeout_seconds))
        if not self.responses:
            raise AssertionError(f"unexpected command: {command!r}")
        return self.responses.pop(0)


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

    def test_rejects_invalid_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "host:port"):
            AdbHmiPowerController(target="192.168.1.39")


if __name__ == "__main__":
    unittest.main()
