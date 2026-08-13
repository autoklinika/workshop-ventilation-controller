import unittest
from pathlib import Path


UNIT_PATH = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "systemd"
    / "ventilation-core.service"
)


class SystemdUnitTest(unittest.TestCase):
    def test_supervised_workers_receive_graceful_shutdown_from_parent(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("KillSignal=SIGTERM", unit)
        self.assertIn("KillMode=mixed", unit)

    def test_stop_timeout_covers_orderly_worker_cleanup(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")
        timeout_line = next(
            line for line in unit.splitlines() if line.startswith("TimeoutStopSec=")
        )
        timeout_seconds = int(timeout_line.partition("=")[2])

        self.assertGreaterEqual(timeout_seconds, 20)

    def test_aero_bus_is_explicitly_configured_read_only_runtime(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("--aero-port /dev/ttyAMA4", unit)
        self.assertIn("--aero-address 44", unit)
        self.assertIn("--aero-baud 9600", unit)
        self.assertIn("--aero-inter-register-delay 0.050", unit)
        self.assertNotIn("--aero-write", unit)

    def test_both_tacho_channels_are_explicitly_enabled(self) -> None:
        unit = UNIT_PATH.read_text(encoding="utf-8")

        self.assertIn("--enable-supply-tacho", unit)
        self.assertIn("--supply-tacho-line GPIO17", unit)
        self.assertIn("--enable-extract-tacho", unit)
        self.assertIn("--extract-tacho-line GPIO27", unit)
        self.assertIn("--tacho-chip /dev/gpiochip0", unit)


if __name__ == "__main__":
    unittest.main()
