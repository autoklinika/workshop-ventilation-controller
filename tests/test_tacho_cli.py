from __future__ import annotations

import argparse
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.hardware.tacho_cli import (
    TachoDiagnosticError,
    format_reading,
    gpiochip_paths,
    resolve_chip_and_offsets,
    validate_args,
)
from ventilation_core.domain.tacho import TachoReading


class FakeChip:
    def __init__(self, path: str, mapping: dict[str, int]) -> None:
        self.path = path
        self.mapping = mapping

    def __enter__(self) -> "FakeChip":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def line_offset_from_id(self, line: str) -> int:
        try:
            return self.mapping[line]
        except KeyError as exc:
            raise ValueError(f"unknown line {line}") from exc


class FakeGpiod:
    def __init__(self, chips: dict[str, dict[str, int]]) -> None:
        self.chips = chips

    def Chip(self, path: str) -> FakeChip:
        if path not in self.chips:
            raise OSError(f"unknown chip {path}")
        return FakeChip(path, self.chips[path])


class TachoCliTest(unittest.TestCase):
    def test_gpiochip_paths_collapses_aliases_of_same_device(self) -> None:
        with (
            patch(
                "tools.hardware.tacho_cli.glob.glob",
                return_value=["/dev/gpiochip0", "/dev/gpiochip4"],
            ),
            patch(
                "tools.hardware.tacho_cli.os.stat",
                side_effect=lambda path, follow_symlinks=True: SimpleNamespace(st_rdev=1234),
            ),
        ):
            self.assertEqual(gpiochip_paths(), ("/dev/gpiochip0",))

    def test_resolves_both_named_lines_on_requested_chip(self) -> None:
        gpiod = FakeGpiod({"/dev/gpiochip0": {"GPIO17": 17, "GPIO27": 27}})

        path, offsets = resolve_chip_and_offsets(
            gpiod,
            ("GPIO17", "GPIO27"),
            requested_chip="/dev/gpiochip0",
        )

        self.assertEqual(path, "/dev/gpiochip0")
        self.assertEqual(offsets, (17, 27))

    def test_rejects_chip_missing_one_required_line(self) -> None:
        gpiod = FakeGpiod({"/dev/gpiochip0": {"GPIO17": 17}})

        with self.assertRaises(TachoDiagnosticError):
            resolve_chip_and_offsets(
                gpiod,
                ("GPIO17", "GPIO27"),
                requested_chip="/dev/gpiochip0",
            )

    def test_formats_valid_reading(self) -> None:
        text = format_reading(
            "SUPPLY",
            TachoReading(
                frequency_hz=113.28,
                rpm=2265.6,
                sample_count=6,
                age_seconds=0.001,
                valid=True,
            ),
        )

        self.assertIn("113.280 Hz", text)
        self.assertIn("2265.6 RPM", text)
        self.assertIn("samples= 6", text)

    def test_formats_invalid_reading(self) -> None:
        text = format_reading("EXTRACT", TachoReading.stopped(age_seconds=0.3))

        self.assertIn("NO VALID TACHO", text)
        self.assertIn("age=0.300s", text)

    def test_validate_args_rejects_same_line(self) -> None:
        args = argparse.Namespace(
            duration=5.0,
            print_interval=1.0,
            supply_line="GPIO17",
            extract_line="GPIO17",
            chip=None,
        )

        with self.assertRaises(TachoDiagnosticError):
            validate_args(args)

    def test_validate_args_rejects_non_positive_duration(self) -> None:
        args = argparse.Namespace(
            duration=0.0,
            print_interval=1.0,
            supply_line="GPIO17",
            extract_line="GPIO27",
            chip=None,
        )

        with self.assertRaises(TachoDiagnosticError):
            validate_args(args)


if __name__ == "__main__":
    unittest.main()
