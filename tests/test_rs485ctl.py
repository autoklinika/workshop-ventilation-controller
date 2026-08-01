import argparse
import unittest
from unittest.mock import patch

from ventilation_core.rs485ctl import _check_ports


class FakeMaster:
    instances = []

    def __init__(self, settings, timeout_seconds: float) -> None:
        self.port = settings.port
        self.ready = True
        self.closed = False
        self.pinged = False
        self.timeout_seconds = timeout_seconds
        self.__class__.instances.append(self)

    def ping(self) -> None:
        self.pinged = True

    def close(self) -> None:
        self.closed = True
        self.ready = False


class RS485CtlTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeMaster.instances = []

    @staticmethod
    def _args(ports: list[str]) -> argparse.Namespace:
        return argparse.Namespace(
            port=ports,
            baudrate=9600,
            parity="N",
            stopbits=1,
            bytesize=8,
            timeout=0.5,
        )

    def test_check_ports_opens_two_independent_workers_without_transmission(self) -> None:
        with patch("ventilation_core.rs485ctl.ProcessRS485Master", FakeMaster):
            response = _check_ports(self._args(["/dev/ttyAMA0", "/dev/ttyAMA2"]))

        self.assertTrue(response["ok"])
        self.assertEqual(response["count"], 2)
        self.assertFalse(response["transmitted"])
        self.assertEqual(
            [entry["port"] for entry in response["ports"]],
            ["/dev/ttyAMA0", "/dev/ttyAMA2"],
        )
        self.assertTrue(all(instance.pinged for instance in FakeMaster.instances))
        self.assertTrue(all(instance.closed for instance in FakeMaster.instances))

    def test_check_ports_rejects_duplicate_uart(self) -> None:
        with self.assertRaisesRegex(ValueError, "only once"):
            _check_ports(self._args(["/dev/ttyAMA0", "/dev/ttyAMA0"]))
