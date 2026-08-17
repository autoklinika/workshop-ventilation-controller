import unittest

from ventilation_core.infrastructure.sen55_modbus import (
    UnsupportedMapVersion,
    decode_sensor_registers,
)


class Sen55ModbusDecoderTests(unittest.TestCase):
    def test_decodes_map_v1_to_normalized_values(self) -> None:
        registers = [
            12,       # PM1.0 = 1.2
            34,       # PM2.5 = 3.4
            56,       # PM4.0 = 5.6
            78,       # PM10 = 7.8
            4567,     # RH = 45.67
            0xF63C,   # T = -25.00
            1234,     # VOC = 123.4
            321,      # NOx = 32.1
            0x00FF,   # all fields available
            0x0003,   # valid + sensor present, legacy firmware
            2,        # age
            5,        # sensor errors
            6,        # Modbus service errors
            0x0001,   # uptime high
            0x0002,   # uptime low
            0x0003,   # firmware 0.3
            1,        # map version
            0x0004,   # sequence high
            0x0005,   # sequence low
        ]

        sample = decode_sensor_registers(registers)

        self.assertEqual(sample.reading.pm1_0_ug_m3, 1.2)
        self.assertEqual(sample.reading.pm2_5_ug_m3, 3.4)
        self.assertEqual(sample.reading.pm4_0_ug_m3, 5.6)
        self.assertEqual(sample.reading.pm10_0_ug_m3, 7.8)
        self.assertEqual(sample.reading.humidity_percent, 45.67)
        self.assertEqual(sample.reading.temperature_celsius, -25.0)
        self.assertEqual(sample.reading.voc_index, 123.4)
        self.assertEqual(sample.reading.nox_index, 32.1)
        self.assertTrue(sample.measurement_valid)
        self.assertFalse(sample.measurement_stale)
        self.assertTrue(sample.sensor_present)
        self.assertEqual(sample.age_seconds, 2)
        self.assertEqual(sample.uptime_seconds, 0x00010002)
        self.assertEqual(sample.firmware_version, "0.3")
        self.assertEqual(sample.map_version, 1)
        self.assertEqual(sample.sequence, 0x00040005)
        self.assertFalse(sample.sen55_device_status_supported)
        self.assertFalse(sample.sen55_device_status_valid)

    def test_decodes_backwards_compatible_sen55_device_status_extension(self) -> None:
        registers = [0] * 19
        registers[8] = 0x00FF
        registers[9] = (
            0x0003  # measurement valid + sensor present
            | (1 << 8)   # status supported
            | (1 << 9)   # status valid
            | (1 << 10)  # fan speed warning
            | (1 << 11)  # fan cleaning info
            | (1 << 12)  # gas error
            | (1 << 13)  # RHT error
            | (1 << 14)  # laser error
            | (1 << 15)  # fan error
        )
        registers[10] = 0
        registers[15] = 0x0006
        registers[16] = 1

        sample = decode_sensor_registers(registers)

        self.assertTrue(sample.measurement_valid)
        self.assertTrue(sample.sen55_device_status_supported)
        self.assertTrue(sample.sen55_device_status_valid)
        self.assertTrue(sample.sen55_fan_speed_warning)
        self.assertTrue(sample.sen55_fan_cleaning)
        self.assertTrue(sample.sen55_gas_sensor_error)
        self.assertTrue(sample.sen55_rht_error)
        self.assertTrue(sample.sen55_laser_error)
        self.assertTrue(sample.sen55_fan_error)
        self.assertEqual(sample.firmware_version, "0.6")
        self.assertEqual(sample.map_version, 1)

    def test_status_flags_are_ignored_when_device_status_is_invalid(self) -> None:
        registers = [0] * 19
        registers[8] = 0x00FF
        registers[9] = 0x0003 | (1 << 8) | (1 << 10) | (1 << 15)
        registers[10] = 0
        registers[16] = 1

        sample = decode_sensor_registers(registers)

        self.assertTrue(sample.sen55_device_status_supported)
        self.assertFalse(sample.sen55_device_status_valid)
        self.assertTrue(sample.sen55_fan_speed_warning)
        self.assertTrue(sample.sen55_fan_error)

    def test_unavailable_fields_are_none(self) -> None:
        registers = [0] * 19
        registers[8] = 1 << 1
        registers[9] = 0x0003
        registers[1] = 250
        registers[10] = 0
        registers[16] = 1

        sample = decode_sensor_registers(registers)

        self.assertIsNone(sample.reading.pm1_0_ug_m3)
        self.assertEqual(sample.reading.pm2_5_ug_m3, 25.0)
        self.assertIsNone(sample.reading.temperature_celsius)
        self.assertTrue(sample.measurement_valid)

    def test_stale_sample_is_not_valid_for_control(self) -> None:
        registers = [0] * 19
        registers[8] = 0x00FF
        registers[9] = 0x0007
        registers[10] = 10
        registers[16] = 1

        sample = decode_sensor_registers(registers)

        self.assertTrue(sample.measurement_stale)
        self.assertFalse(sample.measurement_valid)

    def test_missing_first_measurement_is_not_valid(self) -> None:
        registers = [0] * 19
        registers[8] = 0x00FF
        registers[9] = 0x0003
        registers[10] = 0xFFFF
        registers[16] = 1

        sample = decode_sensor_registers(registers)

        self.assertIsNone(sample.age_seconds)
        self.assertFalse(sample.measurement_valid)

    def test_unknown_map_is_rejected_before_value_decoding(self) -> None:
        registers = [0xFFFF] * 19
        registers[16] = 2

        with self.assertRaises(UnsupportedMapVersion) as context:
            decode_sensor_registers(registers)

        self.assertEqual(context.exception.received, 2)
        self.assertEqual(context.exception.expected, 1)


if __name__ == "__main__":
    unittest.main()
