import struct
import unittest
from unittest.mock import patch

from ventilation_core.domain.aero import AeroBusState
from ventilation_core.infrastructure.aero4a2 import (
    CONFIRMED_TELEMETRY_REGISTERS,
    AeroTelemetryError,
    decode_aero_telemetry,
)
from ventilation_core.infrastructure.aero_bus_worker import (
    AeroBusConfig,
    _poll_aero,
)
from ventilation_core.infrastructure.modbus_rtu import (
    append_crc,
    read_holding_registers,
)


class FakePort:
    timeout = 0.1

    def __init__(self, response: bytes = b"") -> None:
        self.response = bytearray(response)
        self.written = b""
        self.input_resets = 0
        self.flushed = False

    def reset_input_buffer(self) -> None:
        self.input_resets += 1

    def write(self, data: bytes) -> int:
        self.written = data
        return len(data)

    def flush(self) -> None:
        self.flushed = True

    def read(self, size: int) -> bytes:
        chunk = bytes(self.response[:size])
        del self.response[:size]
        return chunk


def valid_snapshot() -> dict[int, int]:
    return {
        2016: 456,
        2021: 215,
        2022: 0xFFFB,
        2023: 73,
        2033: 42,
        2034: 57,
    }


def initial_state(config: AeroBusConfig) -> AeroBusState:
    return AeroBusState(
        port=config.port,
        baudrate=config.baudrate,
        slave_address=config.slave_address,
        register_addresses=config.register_addresses,
        inter_register_delay_seconds=config.inter_register_delay_seconds,
        poll_interval_seconds=config.poll_interval_seconds,
    )


class AeroTelemetryTests(unittest.TestCase):
    def test_reads_holding_register_with_fc03(self) -> None:
        payload = struct.pack(">H", 456)
        response = append_crc(bytes((44, 3, len(payload))) + payload)
        port = FakePort(response)

        received = read_holding_registers(
            port,
            slave_address=44,
            start_address=2016,
            quantity=1,
            timeout_seconds=0.1,
        )

        self.assertEqual(received, [456])
        expected_request = append_crc(struct.pack(">BBHH", 44, 3, 2016, 1))
        self.assertEqual(port.written, expected_request)
        self.assertEqual(port.input_resets, 1)
        self.assertTrue(port.flushed)

    def test_decodes_confirmed_nano_v630_registers(self) -> None:
        telemetry = decode_aero_telemetry(valid_snapshot())

        self.assertEqual(telemetry.humidity_percent, 45.6)
        self.assertEqual(telemetry.supply_temperature_celsius, 21.5)
        self.assertEqual(telemetry.extract_temperature_celsius, -0.5)
        self.assertEqual(telemetry.outdoor_temperature_celsius, 7.3)
        self.assertEqual(telemetry.fan_1_percent, 42)
        self.assertEqual(telemetry.fan_2_percent, 57)

    def test_rejects_missing_confirmed_register(self) -> None:
        registers = valid_snapshot()
        del registers[2023]

        with self.assertRaisesRegex(AeroTelemetryError, "Missing confirmed"):
            decode_aero_telemetry(registers)

    def test_rejects_out_of_range_fan_power(self) -> None:
        registers = valid_snapshot()
        registers[2033] = 101

        with self.assertRaisesRegex(AeroTelemetryError, "fan power"):
            decode_aero_telemetry(registers)

    def test_poll_reads_only_confirmed_registers_individually(self) -> None:
        config = AeroBusConfig(inter_register_delay_seconds=0.0)
        requested: list[tuple[int, int]] = []
        snapshot = valid_snapshot()

        def fake_read(port, slave_address, start_address, quantity, timeout_seconds):
            requested.append((start_address, quantity))
            return [snapshot[start_address]]

        with patch(
            "ventilation_core.infrastructure.aero_bus_worker.read_holding_registers",
            side_effect=fake_read,
        ):
            state = _poll_aero(FakePort(), config, initial_state(config))

        self.assertEqual(
            requested,
            [(address, 1) for address in CONFIRMED_TELEMETRY_REGISTERS],
        )
        self.assertTrue(state.online)
        self.assertTrue(state.usable)
        self.assertEqual(state.successful_polls, 1)

    def test_poll_reports_transport_failure_without_crashing_worker(self) -> None:
        config = AeroBusConfig(timeout_seconds=0.01, inter_register_delay_seconds=0.0)

        state = _poll_aero(FakePort(), config, initial_state(config))

        self.assertFalse(state.online)
        self.assertFalse(state.usable)
        self.assertEqual(state.polls, 1)
        self.assertEqual(state.successful_polls, 0)
        self.assertEqual(state.communication_errors, 1)
        self.assertEqual(state.consecutive_failures, 1)

    def test_invalid_payload_stays_online_but_is_not_usable(self) -> None:
        config = AeroBusConfig(inter_register_delay_seconds=0.0)
        snapshot = valid_snapshot()
        snapshot[2034] = 150

        with patch(
            "ventilation_core.infrastructure.aero_bus_worker.read_holding_registers",
            side_effect=lambda port, slave_address, start_address, quantity, timeout_seconds: [
                snapshot[start_address]
            ],
        ):
            state = _poll_aero(FakePort(), config, initial_state(config))

        self.assertTrue(state.online)
        self.assertFalse(state.usable)
        self.assertEqual(state.polls, 1)
        self.assertEqual(state.successful_polls, 1)
        self.assertEqual(state.communication_errors, 0)
        self.assertEqual(state.invalid_samples, 1)
        self.assertIsNotNone(state.last_success_at)


if __name__ == "__main__":
    unittest.main()
