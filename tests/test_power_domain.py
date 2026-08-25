from __future__ import annotations

from types import SimpleNamespace
import unittest

from ventilation_core.power_domain import Dfr0473PowerDomain, PowerDomainError


class _FakeRequest:
    def __init__(self, events: list[object]) -> None:
        self.events = events
        self.released = False

    def set_value(self, offset: int, value: object) -> None:
        self.events.append(("set", offset, value))

    def release(self) -> None:
        self.released = True
        self.events.append("release")


class _FakeChip:
    def __init__(self, path: str, events: list[object]) -> None:
        self.path = path
        self.events = events

    def __enter__(self):
        self.events.append(("chip-open", self.path))
        return self

    def __exit__(self, exc_type, exc, tb):
        self.events.append("chip-close")

    def line_offset_from_id(self, line_name: str) -> int:
        self.events.append(("line", line_name))
        return 22


class _FakeGpiod:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.request = _FakeRequest(self.events)
        self.line = SimpleNamespace(
            Direction=SimpleNamespace(OUTPUT="OUTPUT"),
            Value=SimpleNamespace(INACTIVE="LOW", ACTIVE="HIGH"),
        )

    def Chip(self, path: str):
        return _FakeChip(path, self.events)

    def LineSettings(self, **kwargs):
        self.events.append(("settings", kwargs))
        return kwargs

    def request_lines(self, path: str, *, consumer: str, config: dict):
        self.events.append(("request", path, consumer, config))
        return self.request


class Dfr0473PowerDomainTest(unittest.TestCase):
    def test_start_claims_gpio_low_before_commanding_high_then_waits(self) -> None:
        fake = _FakeGpiod()
        sleeps: list[float] = []
        domain = Dfr0473PowerDomain(
            chip_path="/dev/gpiochip0",
            line_name="GPIO22",
            stabilization_seconds=1.25,
            sleep=sleeps.append,
            gpiod_module=fake,
        )

        domain.start()

        settings_event = next(event for event in fake.events if isinstance(event, tuple) and event[0] == "settings")
        self.assertEqual(settings_event[1]["direction"], "OUTPUT")
        self.assertEqual(settings_event[1]["output_value"], "LOW")
        self.assertIn(("set", 22, "HIGH"), fake.events)
        self.assertEqual(sleeps, [1.25])
        self.assertTrue(domain.commanded_on)

    def test_power_off_drives_low_and_close_releases_request(self) -> None:
        fake = _FakeGpiod()
        domain = Dfr0473PowerDomain(
            stabilization_seconds=0.0,
            gpiod_module=fake,
        )
        domain.start()
        domain.power_off()
        self.assertFalse(domain.commanded_on)
        self.assertEqual(fake.events[-1], ("set", 22, "LOW"))

        domain.close()
        self.assertTrue(fake.request.released)
        self.assertFalse(domain.commanded_on)
        self.assertIn("release", fake.events)

    def test_power_off_before_start_is_rejected(self) -> None:
        domain = Dfr0473PowerDomain(
            stabilization_seconds=0.0,
            gpiod_module=_FakeGpiod(),
        )
        with self.assertRaisesRegex(PowerDomainError, "not started"):
            domain.power_off()


if __name__ == "__main__":
    unittest.main()
