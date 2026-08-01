import tempfile
import unittest
from pathlib import Path

from ventilation_core.rs485.ports import discover_serial_ports


class RS485PortDiscoveryTest(unittest.TestCase):
    def test_duplicate_paths_are_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "ttyUSB0"
            target.touch()
            alias = root / "adapter-link"
            alias.symlink_to(target)
            ports = discover_serial_ports([str(target), str(alias)])
            self.assertEqual(len(ports), 1)
            self.assertEqual(ports[0].resolved_path, str(target))

    def test_missing_candidates_are_ignored(self) -> None:
        self.assertEqual(discover_serial_ports(["/missing/ttyUSB99"]), [])
