import tempfile
import unittest
from pathlib import Path

from ventilation_core.rs485.ports import (
    _interface_type,
    _path_priority,
    _usable_for_rs485,
    discover_serial_ports,
)


class RS485PortDiscoveryTest(unittest.TestCase):
    def test_duplicate_paths_are_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "ttyAMA0"
            target.touch()
            alias = root / "serial0"
            alias.symlink_to(target)
            ports = discover_serial_ports([str(target), str(alias)])
            self.assertEqual(len(ports), 1)
            self.assertEqual(ports[0].resolved_path, str(target))

    def test_missing_candidates_are_ignored(self) -> None:
        self.assertEqual(discover_serial_ports(["/missing/ttyAMA99"]), [])

    def test_onboard_uart_is_classified(self) -> None:
        self.assertEqual(
            _interface_type("/dev/serial0", "/dev/ttyAMA0"),
            "onboard-uart",
        )
        self.assertEqual(
            _interface_type("/dev/ttyAMA2", "/dev/ttyAMA2"),
            "onboard-uart",
        )

    def test_pi5_debug_uart_is_not_usable_for_rs485(self) -> None:
        interface_type = _interface_type("/dev/serial0", "/dev/ttyAMA10")
        self.assertEqual(interface_type, "debug-uart")
        self.assertFalse(_usable_for_rs485(interface_type))

    def test_regular_uart_is_usable_for_rs485(self) -> None:
        self.assertTrue(_usable_for_rs485("onboard-uart"))
        self.assertTrue(_usable_for_rs485("usb-serial"))

    def test_usb_serial_is_classified(self) -> None:
        self.assertEqual(
            _interface_type("/dev/serial/by-id/adapter", "/dev/ttyUSB0"),
            "usb-serial",
        )

    def test_serial_alias_is_preferred_over_raw_uart_name(self) -> None:
        self.assertLess(_path_priority("/dev/serial0"), _path_priority("/dev/ttyAMA0"))
