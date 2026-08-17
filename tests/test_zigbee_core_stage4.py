from __future__ import annotations

import unittest

from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.zigbee import ZigbeeMqttState, ZigbeeTemperatureSensorState
from ventilation_core.infrastructure.zigbee_mqtt_monitor import (
    ZigbeeDeviceConfig,
    ZigbeeMqttConfig,
    merge_device_payload,
)


class ZigbeeCoreStage4Tests(unittest.TestCase):
    def test_merges_snzb02ld_payload_into_domain_state(self) -> None:
        previous = ZigbeeTemperatureSensorState(
            role="supply",
            friendly_name="temp_nawiew",
            ieee_address="0xa4c13810e66fffff",
            topic="zigbee2mqtt/temp_nawiew",
        )
        updated = merge_device_payload(
            previous,
            {
                "battery": 100,
                "last_seen": "2026-08-17T21:55:05.368Z",
                "linkquality": 120,
                "temperature": 31.3,
                "temperature_calibration": 0,
                "temperature_units": "celsius",
            },
            received_at="2026-08-17T21:55:05.500000+00:00",
        )

        self.assertEqual(updated.temperature_celsius, 31.3)
        self.assertEqual(updated.battery_percent, 100.0)
        self.assertEqual(updated.linkquality, 120)
        self.assertEqual(updated.last_seen, "2026-08-17T21:55:05.368Z")
        self.assertEqual(updated.messages, 1)
        self.assertIsNone(updated.last_error)

    def test_rejects_invalid_battery_without_inventing_value(self) -> None:
        previous = ZigbeeTemperatureSensorState(
            role="extract",
            friendly_name="temp_wywiew",
            ieee_address="0xa4c13810bdedffff",
            topic="zigbee2mqtt/temp_wywiew",
        )
        with self.assertRaises(ValueError):
            merge_device_payload(
                previous,
                {"battery": 150, "temperature": 28.1},
                received_at="2026-08-17T21:55:00+00:00",
            )

    def test_config_requires_unique_device_roles_and_names(self) -> None:
        with self.assertRaises(ValueError):
            ZigbeeMqttConfig(
                devices=(
                    ZigbeeDeviceConfig(role="supply", friendly_name="temp_nawiew"),
                    ZigbeeDeviceConfig(role="supply", friendly_name="temp_wywiew"),
                )
            )

    def test_core_state_serializes_zigbee_without_changing_control_state(self) -> None:
        device = ZigbeeTemperatureSensorState(
            role="supply",
            friendly_name="temp_nawiew",
            ieee_address="0xa4c13810e66fffff",
            topic="zigbee2mqtt/temp_nawiew",
            available=True,
            temperature_celsius=28.5,
            battery_percent=100.0,
            linkquality=83,
        )
        zigbee = ZigbeeMqttState(
            broker_host="127.0.0.1",
            broker_port=1883,
            base_topic="zigbee2mqtt",
            running=True,
            connected=True,
            devices=(device,),
        )
        state = CoreState(
            mode=VentilationMode.STOP,
            setpoints=FanSetpoints.stopped(),
            hardware_ready=True,
            zigbee=zigbee,
        )

        payload = state.to_dict()
        self.assertEqual(payload["mode"], "STOP")
        self.assertEqual(payload["setpoints"], {"supply_voltage": 0.0, "extract_voltage": 0.0})
        self.assertTrue(payload["zigbee"]["connected"])
        self.assertEqual(
            payload["zigbee"]["devices"][0]["temperature_celsius"],
            28.5,
        )


if __name__ == "__main__":
    unittest.main()
