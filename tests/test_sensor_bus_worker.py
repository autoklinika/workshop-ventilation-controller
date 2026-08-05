import struct
import unittest

from ventilation_core.domain.sensors import AirQualityReading, SensorNodeState
from ventilation_core.infrastructure.modbus_rtu import append_crc
from ventilation_core.infrastructure.sensor_bus_worker import (
    SensorBusConfig,
    _poll_node,
)


class FakePort:
    timeout = 0.001

    def __init__(self, response: bytes) -> None:
        self.response = bytearray(response)

    def reset_input_buffer(self) -> None:
        pass

    def write(self, data: bytes) -> int:
        return len(data)

    def flush(self) -> None:
        pass

    def read(self, size: int) -> bytes:
        chunk = bytes(self.response[:size])
        del self.response[:size]
        return chunk


def response_for(slave_address: int, registers: list[int]) -> bytes:
    payload = struct.pack(">19H", *registers)
    return append_crc(bytes((slave_address, 4, len(payload))) + payload)


def valid_registers(*, map_version: int = 1) -> list[int]:
    registers = [0] * 19
    registers[0] = 123
    registers[8] = 0x0001
    registers[9] = 0x0003
    registers[10] = 0
    registers[15] = 0x0002
    registers[16] = map_version
    registers[18] = 1
    return registers


class SensorBusWorkerTests(unittest.TestCase):
    def test_unknown_map_stays_online_but_clears_decoded_values(self) -> None:
        previous = SensorNodeState(
            slave_address=1,
            online=True,
            usable=True,
            reading=AirQualityReading(pm1_0_ug_m3=12.3),
            successful_polls=4,
        )
        state = _poll_node(
            FakePort(response_for(1, valid_registers(map_version=2))),
            SensorBusConfig(timeout_seconds=0.001),
            previous,
        )

        self.assertTrue(state.online)
        self.assertFalse(state.usable)
        self.assertFalse(state.measurement_valid)
        self.assertEqual(state.map_version, 2)
        self.assertEqual(state.map_version_errors, 1)
        self.assertEqual(state.successful_polls, 5)
        self.assertEqual(state.communication_errors, 0)
        self.assertIsNone(state.reading.pm1_0_ug_m3)
        self.assertIn("Unsupported register map 2", state.last_error or "")

    def test_timeout_of_one_node_does_not_prevent_next_node_poll(self) -> None:
        config = SensorBusConfig(timeout_seconds=0.001)
        node_1 = _poll_node(FakePort(b""), config, SensorNodeState(slave_address=1))
        node_2 = _poll_node(
            FakePort(response_for(2, valid_registers())),
            config,
            SensorNodeState(slave_address=2),
        )

        self.assertFalse(node_1.online)
        self.assertEqual(node_1.communication_errors, 1)
        self.assertTrue(node_2.online)
        self.assertTrue(node_2.usable)
        self.assertEqual(node_2.communication_errors, 0)


if __name__ == "__main__":
    unittest.main()
