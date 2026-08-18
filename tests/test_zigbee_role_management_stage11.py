import tempfile
import unittest
from pathlib import Path
from threading import RLock

from ventilation_core.domain.zigbee import (
    ZigbeeInventoryDevice,
    ZigbeeMqttState,
    ZigbeeTemperatureSensorState,
)
from ventilation_core.infrastructure.zigbee_managed_monitor import ManagedReliableZigbeeMqttMonitor
from ventilation_core.infrastructure.zigbee_mqtt_monitor import ZigbeeDeviceConfig, ZigbeeMqttConfig
from ventilation_core.infrastructure.zigbee_role_store import ZigbeeRoleStore
from ventilation_core.web.app import WebApplication


SUPPLY_IEEE = "0xa4c13810e66fffff"
EXTRACT_IEEE = "0xa4c13810bdedffff"


class FakeCoreClient:
    def __init__(self):
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return {"ok": True, "zigbee_management": {"status": "ok"}, "state": {}}


class CaptureRoleStore:
    def __init__(self):
        self.saved = []

    def save_configs(self, configs):
        self.saved.append(tuple(configs))


class ZigbeeRoleManagementStage11Tests(unittest.TestCase):
    def test_role_store_seeds_and_persists_unassigned_role(self):
        defaults = (
            ZigbeeDeviceConfig("supply", "temp_nawiew", SUPPLY_IEEE),
            ZigbeeDeviceConfig("extract", "temp_wywiew", EXTRACT_IEEE),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zigbee-roles.json"
            store = ZigbeeRoleStore(path)
            seeded = store.load_or_seed(defaults)
            self.assertEqual([item.friendly_name for item in seeded], ["temp_nawiew", "temp_wywiew"])
            self.assertTrue(path.is_file())

            store.save_configs(
                (
                    ZigbeeDeviceConfig("supply", "__unassigned_supply__", None),
                    ZigbeeDeviceConfig("extract", "temp_wywiew", EXTRACT_IEEE),
                )
            )
            loaded = store.load_or_seed(defaults)
            self.assertEqual(loaded[0].role, "supply")
            self.assertIsNone(loaded[0].ieee_address)
            self.assertTrue(loaded[0].friendly_name.startswith("__unassigned_"))
            self.assertEqual(loaded[1].ieee_address, EXTRACT_IEEE)

    def test_web_api_exposes_only_explicit_rename_and_role_intents(self):
        core = FakeCoreClient()
        app = WebApplication(core)

        response = app.handle(
            "POST",
            "/api/v1/zigbee/rename",
            {"device_id": SUPPLY_IEEE, "new_name": "kanal_nawiew"},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            core.requests[-1],
            {
                "command": "zigbee-rename-device",
                "device_id": SUPPLY_IEEE,
                "new_name": "kanal_nawiew",
            },
        )

        response = app.handle(
            "POST",
            "/api/v1/zigbee/role",
            {"device_id": SUPPLY_IEEE, "role": None},
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            core.requests[-1],
            {"command": "zigbee-assign-role", "device_id": SUPPLY_IEEE, "role": None},
        )
        self.assertEqual(app.handle("POST", "/api/v1/zigbee/role", {"device_id": SUPPLY_IEEE, "role": "x"}).status, 400)
        self.assertEqual(app.handle("POST", "/api/v1/zigbee/publish", {}).status, 404)

    def test_managed_monitor_renames_assigned_device_and_updates_role_topic(self):
        monitor, capture, calls = self.make_monitor()
        result = monitor.rename_device(SUPPLY_IEEE, "kanal_nawiew")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(calls[-1], ("device/rename", {"from": SUPPLY_IEEE, "to": "kanal_nawiew"}))
        state = monitor.state()
        supply = next(device for device in state.devices if device.role == "supply")
        self.assertEqual(supply.friendly_name, "kanal_nawiew")
        self.assertEqual(supply.topic, "zigbee2mqtt/kanal_nawiew")
        self.assertEqual(capture.saved[-1][0].friendly_name, "kanal_nawiew")

    def test_unassign_hides_role_and_reassign_restores_it_with_retain(self):
        monitor, capture, calls = self.make_monitor()
        monitor.assign_role(SUPPLY_IEEE, None)
        self.assertEqual({device.role for device in monitor.state().devices}, {"extract"})
        self.assertIsNone(capture.saved[-1][0].ieee_address)

        monitor.assign_role(SUPPLY_IEEE, "supply")
        self.assertIn(
            ("device/options", {"id": SUPPLY_IEEE, "options": {"retain": True}}),
            calls,
        )
        roles = {device.role: device.ieee_address for device in monitor.state().devices}
        self.assertEqual(roles["supply"], SUPPLY_IEEE)
        self.assertEqual(roles["extract"], EXTRACT_IEEE)

    def test_role_conflict_requires_explicit_unassign_first(self):
        monitor, _capture, _calls = self.make_monitor()
        with self.assertRaisesRegex(ValueError, "already assigned"):
            monitor.assign_role(SUPPLY_IEEE, "extract")

    def test_name_validation_rejects_mqtt_topic_wildcards_and_reserved_names(self):
        self.assertEqual(ManagedReliableZigbeeMqttMonitor._validate_name("temp_nawiew_2"), "temp_nawiew_2")
        for value in ("", "bad/name", "bad#name", "bridge", "__unassigned_supply__"):
            with self.assertRaises(ValueError):
                ManagedReliableZigbeeMqttMonitor._validate_name(value)

    def make_monitor(self):
        capture = CaptureRoleStore()
        configs = (
            ZigbeeDeviceConfig("supply", "temp_nawiew", SUPPLY_IEEE),
            ZigbeeDeviceConfig("extract", "temp_wywiew", EXTRACT_IEEE),
        )
        monitor = ManagedReliableZigbeeMqttMonitor.__new__(ManagedReliableZigbeeMqttMonitor)
        monitor._role_store = capture
        monitor._lock = RLock()
        monitor._closed = False
        monitor._config = ZigbeeMqttConfig(devices=configs)
        monitor._devices = {
            "supply": ZigbeeTemperatureSensorState(
                role="supply",
                friendly_name="temp_nawiew",
                ieee_address=SUPPLY_IEEE,
                topic="zigbee2mqtt/temp_nawiew",
                temperature_celsius=25.0,
                messages=1,
            ),
            "extract": ZigbeeTemperatureSensorState(
                role="extract",
                friendly_name="temp_wywiew",
                ieee_address=EXTRACT_IEEE,
                topic="zigbee2mqtt/temp_wywiew",
                temperature_celsius=26.0,
                messages=1,
            ),
        }
        monitor._topic_to_role = {
            "zigbee2mqtt/temp_nawiew": "supply",
            "zigbee2mqtt/temp_wywiew": "extract",
        }
        monitor._availability_to_role = {
            "zigbee2mqtt/temp_nawiew/availability": "supply",
            "zigbee2mqtt/temp_wywiew/availability": "extract",
        }
        inventory = (
            ZigbeeInventoryDevice("0x00124b0038aaf159", "Coordinator", "Coordinator", False, False),
            ZigbeeInventoryDevice(SUPPLY_IEEE, "temp_nawiew", "EndDevice", True, False, model="SNZB-02LD"),
            ZigbeeInventoryDevice(EXTRACT_IEEE, "temp_wywiew", "EndDevice", True, False, model="SNZB-02LD"),
        )
        monitor._state = ZigbeeMqttState(
            broker_host="127.0.0.1",
            broker_port=1883,
            base_topic="zigbee2mqtt",
            running=True,
            connected=False,
            bridge_online=True,
            inventory=inventory,
            inventory_updated_at="2026-08-18T00:00:00+00:00",
            devices=tuple(monitor._devices.values()),
        )
        calls = []

        def bridge_request(suffix, payload):
            calls.append((suffix, payload))
            return {"status": "ok", "data": dict(payload)}

        monitor._bridge_request = bridge_request
        return monitor, capture, calls


if __name__ == "__main__":
    unittest.main()
