import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from threading import RLock

from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.zigbee import ZigbeeMqttState, ZigbeeTemperatureSensorState
from ventilation_core.infrastructure.zigbee_capability_monitor import CapabilityManagedZigbeeMqttMonitor
from ventilation_core.infrastructure.zigbee_mqtt_monitor import ZigbeeDeviceConfig, ZigbeeMqttConfig
from ventilation_core.infrastructure.zigbee_role_store import MULTI_ROLE, ZigbeeRoleRecord, ZigbeeRoleStore
from ventilation_core.runtime.server import CoreServer
from ventilation_core.web.app import WebApplication


SUPPLY = "0xa4c13810e66fffff"
EXTRACT = "0xa4c13810bdedffff"
OUTDOOR = "0xa4c13879a816c919"
EXTRA = "0xa4c13879a816c920"


class FakeCoreClient:
    def __init__(self):
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return {"ok": True, "zigbee_management": {"status": "ok"}, "state": {}}


class RoleService:
    def __init__(self):
        self.calls = []

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

    def zigbee_assign_role(self, device_id, role):
        self.calls.append((device_id, role))
        return {"status": "ok", "data": {"id": device_id, "role": role}}


class ZigbeeSensorListStage14Tests(unittest.TestCase):
    def test_role_store_keeps_multiple_other_devices_and_system_roles(self):
        defaults = (
            ZigbeeDeviceConfig("supply", "temp_nawiew", SUPPLY),
            ZigbeeDeviceConfig("extract", "temp_wywiew", EXTRACT),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zigbee-roles.json"
            store = ZigbeeRoleStore(path)
            store.load_or_seed(defaults)
            store.save_other_records(
                (
                    ZigbeeRoleRecord(MULTI_ROLE, OUTDOOR, "temp_zew"),
                    ZigbeeRoleRecord(MULTI_ROLE, EXTRA, "magazyn"),
                )
            )
            reloaded = ZigbeeRoleStore(path)
            system = reloaded.load_records()
            other = reloaded.load_other_records()
            self.assertEqual({item.role for item in system}, {"supply", "extract"})
            self.assertEqual({item.ieee_address for item in other}, {OUTDOOR, EXTRA})
            self.assertTrue(all(item.role == MULTI_ROLE for item in other))

    def test_core_collects_actual_values_for_every_inventory_sensor(self):
        monitor = self.make_monitor()
        bridge_devices = [
            {
                "ieee_address": "0x00124b0038aaf159",
                "friendly_name": "Coordinator",
                "type": "Coordinator",
                "supported": False,
                "disabled": False,
                "definition": None,
            },
            self.device(SUPPLY, "temp_nawiew", "SNZB-02LD", "SONOFF"),
            self.device(EXTRACT, "temp_wywiew", "SNZB-02LD", "SONOFF"),
            self.device(OUTDOOR, "temp_zew", "TH09Z", "Tuya", humidity=True, voltage=True),
        ]
        monitor._handle_capability_inventory(json.dumps(bridge_devices).encode())
        self.assertEqual(len(monitor._sensor_list_by_ieee), 3)
        self.assertNotIn("0x00124b0038aaf159", monitor._sensor_list_by_ieee)
        self.assertIn("zigbee2mqtt/temp_zew", monitor._generic_topic_to_ieee)

        monitor._handle_generic_payload(
            OUTDOOR,
            json.dumps(
                {
                    "temperature": 18.4,
                    "humidity": 62.3,
                    "battery": 91,
                    "voltage": 2870,
                    "linkquality": 144,
                    "last_seen": "2026-08-18T11:30:00.000Z",
                }
            ).encode(),
        )
        monitor._handle_generic_availability(OUTDOOR, b'{"state":"online"}')
        state = monitor.state()
        row = next(item for item in state.sensor_list if item.ieee_address == OUTDOOR)
        self.assertEqual(row.role, "other")
        self.assertEqual(row.friendly_name, "temp_zew")
        self.assertEqual(row.model, "TH09Z")
        self.assertEqual(row.temperature_celsius, 18.4)
        self.assertEqual(row.humidity_percent, 62.3)
        self.assertEqual(row.battery_percent, 91.0)
        self.assertEqual(row.voltage_mv, 2870.0)
        self.assertEqual(row.linkquality, 144)
        self.assertTrue(row.available)
        self.assertEqual(row.messages, 1)

    def test_web_and_runtime_accept_other_as_explicit_role_only(self):
        core = FakeCoreClient()
        response = WebApplication(core).handle(
            "POST",
            "/api/v1/zigbee/role",
            {"device_id": OUTDOOR, "role": "other"},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            core.requests[-1],
            {"command": "zigbee-assign-role", "device_id": OUTDOOR, "role": "other"},
        )
        self.assertEqual(
            WebApplication(core).handle(
                "POST", "/api/v1/zigbee/role", {"device_id": OUTDOOR, "role": "invalid"}
            ).status,
            400,
        )

        async def scenario():
            service = RoleService()
            server = CoreServer(service, Path("/tmp/unused-zigbee-stage14.sock"), 1.0)
            result = await server._dispatch(
                {"command": "zigbee-assign-role", "device_id": OUTDOOR, "role": "other"}
            )
            self.assertTrue(result["ok"])
            self.assertEqual(service.calls, [(OUTDOOR, "other")])

        asyncio.run(scenario())

    @staticmethod
    def device(ieee, name, model, vendor, *, humidity=False, voltage=False):
        exposes = [
            {"type": "numeric", "name": "temperature", "property": "temperature", "unit": "°C", "access": 1},
            {"type": "numeric", "name": "battery", "property": "battery", "unit": "%", "access": 1},
            {"type": "numeric", "name": "linkquality", "property": "linkquality", "unit": "lqi", "access": 1},
        ]
        if humidity:
            exposes.append({"type": "numeric", "name": "humidity", "property": "humidity", "unit": "%", "access": 1})
        if voltage:
            exposes.append({"type": "numeric", "name": "voltage", "property": "voltage", "unit": "mV", "access": 1})
        return {
            "ieee_address": ieee,
            "friendly_name": name,
            "type": "EndDevice",
            "supported": True,
            "disabled": False,
            "power_source": "Battery",
            "definition": {"model": model, "vendor": vendor, "description": "sensor", "exposes": exposes},
        }

    @staticmethod
    def make_monitor():
        configs = (
            ZigbeeDeviceConfig("supply", "temp_nawiew", SUPPLY),
            ZigbeeDeviceConfig("extract", "temp_wywiew", EXTRACT),
        )
        monitor = CapabilityManagedZigbeeMqttMonitor.__new__(CapabilityManagedZigbeeMqttMonitor)
        monitor._lock = RLock()
        monitor._closed = False
        monitor._config = ZigbeeMqttConfig(devices=configs)
        monitor._devices = {
            "supply": ZigbeeTemperatureSensorState("supply", "temp_nawiew", SUPPLY, "zigbee2mqtt/temp_nawiew"),
            "extract": ZigbeeTemperatureSensorState("extract", "temp_wywiew", EXTRACT, "zigbee2mqtt/temp_wywiew"),
        }
        monitor._topic_to_role = {
            "zigbee2mqtt/temp_nawiew": "supply",
            "zigbee2mqtt/temp_wywiew": "extract",
        }
        monitor._availability_to_role = {
            "zigbee2mqtt/temp_nawiew/availability": "supply",
            "zigbee2mqtt/temp_wywiew/availability": "extract",
        }
        monitor._other_roles = {OUTDOOR: ZigbeeRoleRecord(MULTI_ROLE, OUTDOOR, "temp_zew")}
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
            devices=tuple(monitor._devices.values()),
        )
        return monitor


if __name__ == "__main__":
    unittest.main()
