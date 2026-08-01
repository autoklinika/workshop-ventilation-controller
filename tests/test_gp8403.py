import unittest

from ventilation_core.infrastructure.gp8403 import GP8403, GP8403Config


class FakeBus:
    def __init__(self) -> None:
        self.writes = []
        self.closed = False

    def read_byte(self, address: int) -> int:
        return 0x11

    def write_word_data(self, address: int, register: int, value: int) -> None:
        self.writes.append((address, register, value))

    def close(self) -> None:
        self.closed = True


class GP8403Test(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = FakeBus()
        self.dac = GP8403(GP8403Config(), bus_instance=self.bus)

    def test_voltage_conversion(self) -> None:
        self.assertEqual(self.dac.voltage_to_word(0), 0)
        self.assertEqual(self.dac.voltage_to_word(10), 0xFFF0)

    def test_channel_mapping(self) -> None:
        self.dac.set_both_channels(2, 5)
        self.assertEqual(self.bus.writes[0][1], 0x02)
        self.assertEqual(self.bus.writes[1][1], 0x04)

    def test_zero_all(self) -> None:
        self.dac.zero_all()
        self.assertEqual(self.bus.writes, [(0x58, 0x02, 0), (0x58, 0x04, 0)])
