import json
import unittest
from threading import RLock

from ventilation_core.domain.zigbee import ZigbeeMqttState
from ventilation_core.infrastructure.zigbee_capability_monitor import CapabilityManagedZigbeeMqttMonitor


IEEE = "0xa4c13810e66fffff"


class ZigbeePairingHydrationStage13Tests(unittest.TestCase):
    def test_successful_interview_is_hydrated_from_bridge_devices_exposes(self):
        monitor = CapabilityManagedZigbeeMqttMonitor.__new__(CapabilityManagedZigbeeMqttMonitor)
        monitor._lock = RLock()
        # __new__ deliberately bypasses the live MQTT constructor. Keep this
        # isolated fixture aligned with the monitor's Stage 14 core-owned
        # generic sensor telemetry bookkeeping without creating a broker client.
        monitor._sensor_list_by_ieee = {}
        monitor._generic_topic_to_ieee = {}
        monitor._generic_availability_to_ieee = {}
        monitor._state = ZigbeeMqttState(
            broker_host="127.0.0.1",
            broker_port=1883,
            base_topic="zigbee2mqtt",
            running=True,
            connected=False,
            bridge_online=True,
        )

        # Current Zigbee2MQTT interview events identify the device and definition,
        # while bridge/devices remains the authoritative source of exposes.
        interview = {
            "type": "device_interview",
            "data": {
                "friendly_name": IEEE,
                "status": "successful",
                "ieee_address": IEEE,
                "supported": True,
                "definition": {
                    "model": "SNZB-02LD",
                    "vendor": "SONOFF",
                    "description": "Waterproof temperature sensor",
                },
            },
        }
        monitor._handle_pairing_event(json.dumps(interview).encode())
        self.assertEqual(monitor._state.pairing.status, "successful")
        self.assertEqual(monitor._state.pairing.capabilities, ())

        bridge_devices = [
            {
                "ieee_address": IEEE,
                "friendly_name": "temp_nawiew",
                "type": "EndDevice",
                "supported": True,
                "disabled": False,
                "power_source": "Battery",
                "interview_state": "SUCCESSFUL",
                "definition": {
                    "model": "SNZB-02LD",
                    "vendor": "SONOFF",
                    "description": "Waterproof temperature sensor",
                    "exposes": [
                        {
                            "type": "numeric",
                            "name": "battery",
                            "label": "Battery",
                            "property": "battery",
                            "access": 5,
                            "unit": "%",
                        },
                        {
                            "type": "numeric",
                            "name": "temperature",
                            "label": "Temperature",
                            "property": "temperature",
                            "access": 5,
                            "unit": "°C",
                        },
                        {
                            "type": "enum",
                            "name": "temperature_units",
                            "label": "Temperature units",
                            "property": "temperature_units",
                            "access": 7,
                            "category": "config",
                            "values": ["celsius", "fahrenheit"],
                        },
                    ],
                },
            }
        ]
        monitor._handle_capability_inventory(json.dumps(bridge_devices).encode())

        pairing = monitor._state.pairing
        self.assertEqual(pairing.friendly_name, "temp_nawiew")
        self.assertEqual(pairing.model, "SNZB-02LD")
        self.assertEqual(
            [capability.property for capability in pairing.capabilities],
            ["battery", "temperature"],
        )
        self.assertNotIn(
            "temperature_units",
            {capability.property for capability in pairing.capabilities},
        )
        self.assertIn(IEEE, monitor._sensor_list_by_ieee)
        self.assertEqual(
            monitor._generic_topic_to_ieee["zigbee2mqtt/temp_nawiew"],
            IEEE,
        )


if __name__ == "__main__":
    unittest.main()
