import unittest
from dataclasses import replace
from datetime import datetime, timezone

from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.zigbee_service import ZigbeeAlertingVentilationService
from ventilation_core.domain.models import AlarmCode, FanSetpoints
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.domain.zigbee import (
    ZigbeeInventoryDevice,
    ZigbeeMqttState,
    ZigbeeTemperatureSensorState,
)
from ventilation_core.infrastructure.zigbee_mqtt_monitor import parse_bridge_devices
from ventilation_core.web.app import WebApplication


class FakeCoreClient:
    def __init__(self, response=None):
        self.response = response or {"ok": True, "state": {"zigbee": {}}}
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return self.response


class FakeActuator:
    def __init__(self):
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()

    def apply(self, setpoints):
        self.applied = setpoints

    def stop_all(self):
        self.applied = FanSetpoints.stopped()

    def health_check(self):
        return None

    def recover(self):
        self.ready = True
        self.last_error = None
        self.applied = FanSetpoints.stopped()

    def close(self):
        return None


class FakeZigbee:
    def __init__(self, state):
        self.current_state = state
        self.permit_calls = []
        self.remove_calls = []

    def state(self):
        return self.current_state

    def health_check(self):
        return None

    def permit_join(self, seconds):
        self.permit_calls.append(seconds)
        return {"status": "ok", "data": {"time": seconds}}

    def remove_device(self, device_id):
        self.remove_calls.append(device_id)
        return {"status": "ok", "data": {"id": device_id}}

    def close(self):
        return None


def healthy_zigbee(
    *,
    battery=100.0,
    bridge_online=True,
    inventory=True,
    connected=True,
    last_message_at=None,
):
    now = last_message_at or datetime.now(timezone.utc).isoformat()
    devices = (
        ZigbeeTemperatureSensorState(
            role="supply",
            friendly_name="temp_nawiew",
            ieee_address="0xa4c13810e66fffff",
            topic="zigbee2mqtt/temp_nawiew",
            temperature_celsius=25.0,
            battery_percent=battery,
            linkquality=80,
            last_message_at=now,
            messages=2,
        ),
        ZigbeeTemperatureSensorState(
            role="extract",
            friendly_name="temp_wywiew",
            ieee_address="0xa4c13810bdedffff",
            topic="zigbee2mqtt/temp_wywiew",
            temperature_celsius=25.5,
            battery_percent=100.0,
            linkquality=90,
            last_message_at=now,
            messages=2,
        ),
    )
    inventory_devices = ()
    updated = None
    if inventory:
        updated = now
        inventory_devices = (
            ZigbeeInventoryDevice(
                ieee_address="0x00124b0038aaf159",
                friendly_name="Coordinator",
                device_type="Coordinator",
                supported=False,
                disabled=False,
            ),
            ZigbeeInventoryDevice(
                ieee_address="0xa4c13810e66fffff",
                friendly_name="temp_nawiew",
                device_type="EndDevice",
                supported=True,
                disabled=False,
                model="SNZB-02LD",
                vendor="SONOFF",
            ),
            ZigbeeInventoryDevice(
                ieee_address="0xa4c13810bdedffff",
                friendly_name="temp_wywiew",
                device_type="EndDevice",
                supported=True,
                disabled=False,
                model="SNZB-02LD",
                vendor="SONOFF",
            ),
        )
    return ZigbeeMqttState(
        broker_host="127.0.0.1",
        broker_port=1883,
        base_topic="zigbee2mqtt",
        running=True,
        connected=connected,
        disconnected_at=now if not connected else None,
        last_error="MQTT disconnected" if not connected else None,
        bridge_online=bridge_online,
        permit_join=False,
        inventory_updated_at=updated,
        inventory=inventory_devices,
        devices=devices,
    )


class ZigbeeManagementAndAlertsTests(unittest.TestCase):
    def test_bridge_devices_parser_exposes_inventory(self):
        payload = [
            {
                "ieee_address": "0x00124b0038aaf159",
                "friendly_name": "Coordinator",
                "type": "Coordinator",
                "supported": False,
                "disabled": False,
                "definition": None,
                "interview_state": "SUCCESSFUL",
            },
            {
                "ieee_address": "0xa4c13810e66fffff",
                "friendly_name": "temp_nawiew",
                "type": "EndDevice",
                "supported": True,
                "disabled": False,
                "definition": {
                    "model": "SNZB-02LD",
                    "vendor": "SONOFF",
                    "description": "Waterproof temperature sensor",
                },
                "power_source": "Battery",
                "interview_state": "SUCCESSFUL",
            },
        ]
        inventory = parse_bridge_devices(payload)
        self.assertEqual(len(inventory), 2)
        self.assertTrue(inventory[0].is_coordinator)
        self.assertEqual(inventory[1].model, "SNZB-02LD")
        self.assertEqual(inventory[1].vendor, "SONOFF")

    def test_web_management_endpoints_are_narrow_and_validated(self):
        core = FakeCoreClient({"ok": True, "zigbee_management": {"status": "ok"}, "state": {}})
        app = WebApplication(core)

        response = app.handle("POST", "/api/v1/zigbee/permit-join", {"seconds": 120})
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests[-1], {"command": "zigbee-permit-join", "seconds": 120})

        response = app.handle("POST", "/api/v1/zigbee/remove", {"device_id": "0xabc"})
        self.assertEqual(response.status, 200)
        self.assertEqual(core.requests[-1], {"command": "zigbee-remove-device", "device_id": "0xabc"})

        before = len(core.requests)
        self.assertEqual(app.handle("POST", "/api/v1/zigbee/permit-join", {"seconds": 255}).status, 400)
        self.assertEqual(app.handle("POST", "/api/v1/zigbee/remove", {"device_id": ""}).status, 400)
        self.assertEqual(len(core.requests), before)
        self.assertEqual(app.handle("POST", "/api/v1/zigbee/publish", {}).status, 404)

    def make_service(self, zigbee_state):
        zigbee = FakeZigbee(zigbee_state)
        service = ZigbeeAlertingVentilationService(
            actuator=FakeActuator(),
            policy=FanSetpointPolicy(1.0, 10.0),
            zigbee=zigbee,
            alert_registry=AlertRegistry(MemoryAlertStore()),
        )
        return service, zigbee

    def test_service_management_calls_are_explicit(self):
        service, zigbee = self.make_service(healthy_zigbee())
        service.zigbee_permit_join(120)
        service.zigbee_remove_device("0xa4c13810e66fffff")
        self.assertEqual(zigbee.permit_calls, [120])
        self.assertEqual(zigbee.remove_calls, ["0xa4c13810e66fffff"])
        service.close()

    def test_healthy_zigbee_does_not_create_zigbee_alerts(self):
        service, _ = self.make_service(healthy_zigbee())
        state = service.health_check()
        codes = {alert.code for alert in state.active_alarms}
        self.assertFalse(any(code.value.startswith("ZIGBEE_") for code in codes))
        service.close()

    def test_low_battery_and_bridge_offline_are_core_owned_alerts(self):
        service, zigbee = self.make_service(healthy_zigbee(battery=10.0))
        state = service.health_check()
        codes = {alert.code for alert in state.active_alarms}
        self.assertIn(AlarmCode.ZIGBEE_LOW_BATTERY, codes)

        zigbee.current_state = healthy_zigbee(bridge_online=False)
        state = service.health_check()
        codes = {alert.code for alert in state.active_alarms}
        self.assertIn(AlarmCode.ZIGBEE_BRIDGE_OFFLINE, codes)
        self.assertNotIn(AlarmCode.ZIGBEE_LOW_BATTERY, codes)
        service.close()

    def test_missing_required_device_and_mqtt_disconnect_are_alerts(self):
        missing = healthy_zigbee()
        missing = replace(
            missing,
            inventory=tuple(
                device
                for device in missing.inventory
                if device.friendly_name != "temp_nawiew"
            ),
        )
        service, zigbee = self.make_service(missing)
        state = service.health_check()
        self.assertIn(
            AlarmCode.ZIGBEE_DEVICE_OFFLINE,
            {alert.code for alert in state.active_alarms},
        )

        zigbee.current_state = healthy_zigbee(connected=False)
        state = service.health_check()
        self.assertIn(
            AlarmCode.ZIGBEE_MQTT_DISCONNECTED,
            {alert.code for alert in state.active_alarms},
        )
        service.close()

    def test_stale_data_becomes_warning_without_marking_device_offline(self):
        service, _ = self.make_service(
            healthy_zigbee(last_message_at="2020-01-01T00:00:00+00:00")
        )
        state = service.health_check()
        codes = {alert.code for alert in state.active_alarms}
        self.assertIn(AlarmCode.ZIGBEE_DEVICE_DATA_STALE, codes)
        self.assertNotIn(AlarmCode.ZIGBEE_DEVICE_OFFLINE, codes)
        service.close()


if __name__ == "__main__":
    unittest.main()
