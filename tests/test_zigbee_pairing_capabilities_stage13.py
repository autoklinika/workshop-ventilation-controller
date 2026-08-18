import asyncio
import json
import unittest
from pathlib import Path
from threading import RLock

from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.zigbee import ZigbeeInventoryDevice, ZigbeeMqttState
from ventilation_core.infrastructure.zigbee_capability_monitor import (
    CapabilityManagedZigbeeMqttMonitor,
    parse_bridge_devices_with_capabilities,
    parse_published_capabilities,
)
from ventilation_core.runtime.server import CoreServer
from ventilation_core.web.app import WebApplication


IEEE = "0xa4c13810e66fffff"


class FakeCoreClient:
    def __init__(self):
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return {"ok": True, "zigbee_management": {"status": "ok"}, "state": {}}


class PairingService:
    def __init__(self):
        self.acks = []

    def state(self):
        return CoreState(
            mode=VentilationMode.STOP,
            setpoints=FanSetpoints.stopped(),
            hardware_ready=True,
            zigbee=ZigbeeMqttState(
                broker_host="127.0.0.1",
                broker_port=1883,
                base_topic="zigbee2mqtt",
            ),
        )

    def zigbee_acknowledge_pairing(self, ieee_address):
        self.acks.append(ieee_address)
        return {"status": "ok", "data": {"ieee_address": ieee_address}}


class ZigbeePairingCapabilitiesStage13Tests(unittest.TestCase):
    def test_exposes_are_filtered_to_values_published_by_device(self):
        exposes = [
            {
                "type": "numeric",
                "name": "temperature",
                "property": "temperature",
                "label": "Temperature",
                "unit": "°C",
                "access": 1,
                "value_min": -40,
                "value_max": 125,
            },
            {
                "type": "numeric",
                "name": "battery",
                "property": "battery",
                "label": "Battery",
                "unit": "%",
                "access": 1,
            },
            {
                "type": "numeric",
                "name": "temperature_precision",
                "property": "temperature_precision",
                "access": 2,
                "category": "config",
            },
            {
                "type": "composite",
                "name": "alarm",
                "property": "alarm",
                "access": 0,
                "features": [
                    {
                        "type": "binary",
                        "name": "water_leak",
                        "property": "water_leak",
                        "label": "Water leak",
                        "access": 1,
                    },
                    {
                        "type": "binary",
                        "name": "alarm_enable",
                        "property": "alarm_enable",
                        "access": 2,
                        "category": "config",
                    },
                ],
            },
        ]

        capabilities = parse_published_capabilities(exposes)
        self.assertEqual(
            [item.property for item in capabilities],
            ["temperature", "battery", "water_leak"],
        )
        self.assertEqual(capabilities[0].unit, "°C")
        self.assertEqual(capabilities[0].value_min, -40.0)
        self.assertEqual(capabilities[0].value_max, 125.0)

    def test_bridge_inventory_contains_core_normalized_capabilities(self):
        payload = [
            {
                "ieee_address": IEEE,
                "friendly_name": "temp_nawiew",
                "type": "EndDevice",
                "supported": True,
                "disabled": False,
                "definition": {
                    "model": "SNZB-02LD",
                    "vendor": "SONOFF",
                    "description": "Waterproof temperature sensor",
                    "exposes": [
                        {"type": "numeric", "name": "temperature", "property": "temperature", "unit": "°C", "access": 1},
                        {"type": "numeric", "name": "battery", "property": "battery", "unit": "%", "access": 1},
                    ],
                },
            }
        ]
        inventory = parse_bridge_devices_with_capabilities(payload)
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0].model, "SNZB-02LD")
        self.assertEqual(
            [item.property for item in inventory[0].capabilities],
            ["temperature", "battery"],
        )

    def make_monitor(self):
        monitor = CapabilityManagedZigbeeMqttMonitor.__new__(CapabilityManagedZigbeeMqttMonitor)
        monitor._lock = RLock()
        monitor._state = ZigbeeMqttState(
            broker_host="127.0.0.1",
            broker_port=1883,
            base_topic="zigbee2mqtt",
            running=True,
            connected=True,
            bridge_online=True,
            inventory=(
                ZigbeeInventoryDevice(
                    IEEE,
                    "temp_nawiew",
                    "EndDevice",
                    True,
                    False,
                    model="SNZB-02LD",
                    vendor="SONOFF",
                ),
            ),
        )
        return monitor

    def test_successful_interview_creates_core_owned_pairing_result(self):
        monitor = self.make_monitor()
        payload = {
            "type": "device_interview",
            "data": {
                "status": "successful",
                "ieee_address": IEEE,
                "friendly_name": "temp_nawiew",
                "supported": True,
                "definition": {
                    "model": "SNZB-02LD",
                    "vendor": "SONOFF",
                    "exposes": [
                        {"type": "numeric", "name": "temperature", "property": "temperature", "unit": "°C", "access": 1},
                        {"type": "numeric", "name": "battery", "property": "battery", "unit": "%", "access": 1},
                    ],
                },
            },
        }
        monitor._handle_pairing_event(json.dumps(payload).encode())
        pairing = monitor._state.pairing
        self.assertIsNotNone(pairing)
        self.assertEqual(pairing.status, "successful")
        self.assertEqual(pairing.ieee_address, IEEE)
        self.assertEqual(pairing.model, "SNZB-02LD")
        self.assertEqual([item.property for item in pairing.capabilities], ["temperature", "battery"])
        self.assertFalse(pairing.acknowledged)

        result = monitor.acknowledge_pairing(IEEE)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(monitor._state.pairing.acknowledged)

    def test_web_pairing_ack_is_only_an_explicit_core_intent(self):
        core = FakeCoreClient()
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/zigbee/pairing/ack",
            {"ieee_address": IEEE},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            core.requests[-1],
            {"command": "zigbee-ack-pairing", "ieee_address": IEEE},
        )

    def test_runtime_pairing_ack_is_executed_by_core_service(self):
        async def scenario():
            service = PairingService()
            server = CoreServer(service, Path("/tmp/unused-zigbee-stage13.sock"), 1.0)
            response = await server._dispatch(
                {"command": "zigbee-ack-pairing", "ieee_address": IEEE}
            )
            self.assertTrue(response["ok"])
            self.assertEqual(service.acks, [IEEE])

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
