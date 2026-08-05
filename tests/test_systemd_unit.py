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


if __name__ == "__main__":
    unittest.main()
