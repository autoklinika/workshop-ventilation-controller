import argparse
import unittest
from unittest.mock import patch

from ventilation_core.rs485ctl import _check_ports, _hex_bytes, _loopback


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

    @staticmethod
    def _loopback_args() -> argparse.Namespace:
        return argparse.Namespace(
            port_a="/dev/serial0",
            port_b="/dev/ttyAMA2",
            baudrate=9600,
            parity="N",
            stopbits=1,
            bytesize=8,
            timeout=0.5,
            payload=bytes.fromhex("57 56 43 32 2D 52 53 34 38 35"),
            settle=0.0,
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

    def test_loopback_validates_both_directions_and_closes_workers(self) -> None:
        args = self._loopback_args()
        with (
            patch("ventilation_core.rs485ctl.ProcessRS485Master", FakeMaster),
            patch(
                "ventilation_core.rs485ctl._one_way_loopback",
                return_value=args.payload,
            ) as transfer,
        ):
            response = _loopback(args)

        self.assertTrue(response["ok"])
        self.assertTrue(response["transmitted"])
        self.assertTrue(response["a_to_b"]["matched"])
        self.assertTrue(response["b_to_a"]["matched"])
        self.assertEqual(transfer.call_count, 2)
        self.assertTrue(all(instance.closed for instance in FakeMaster.instances))

    def test_loopback_rejects_same_uart(self) -> None:
        args = self._loopback_args()
        args.port_b = args.port_a
        with self.assertRaisesRegex(ValueError, "two different"):
            _loopback(args)

    def test_hex_payload_parser_accepts_common_separators(self) -> None:
        self.assertEqual(_hex_bytes("57:56-43 32"), bytes.fromhex("57 56 43 32"))
