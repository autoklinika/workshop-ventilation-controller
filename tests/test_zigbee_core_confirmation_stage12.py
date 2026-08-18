import asyncio
import unittest
from pathlib import Path

from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.zigbee import (
    ZigbeeInventoryDevice,
    ZigbeeMqttState,
    ZigbeeTemperatureSensorState,
)
from ventilation_core.runtime.server import CoreServer


SUPPLY_IEEE = "0xa4c13810e66fffff"
EXTRACT_IEEE = "0xa4c13810bdedffff"
COORDINATOR_IEEE = "0x00124b0038aaf159"


class FakeService:
    def __init__(self):
        self.removed = []
        self.remove_error = None
        self._zigbee = ZigbeeMqttState(
            broker_host="127.0.0.1",
            broker_port=1883,
            base_topic="zigbee2mqtt",
            running=True,
            connected=True,
            bridge_online=True,
            inventory=(
                ZigbeeInventoryDevice(
                    COORDINATOR_IEEE,
                    "Coordinator",
                    "Coordinator",
                    False,
                    False,
                ),
                ZigbeeInventoryDevice(
                    SUPPLY_IEEE,
                    "temp_nawiew",
                    "EndDevice",
                    True,
                    False,
                    model="SNZB-02LD",
                ),
                ZigbeeInventoryDevice(
                    EXTRACT_IEEE,
                    "temp_wywiew",
                    "EndDevice",
                    True,
                    False,
                    model="SNZB-02LD",
                ),
            ),
            devices=(
                ZigbeeTemperatureSensorState(
                    role="supply",
                    friendly_name="temp_nawiew",
                    ieee_address=SUPPLY_IEEE,
                    topic="zigbee2mqtt/temp_nawiew",
                ),
                ZigbeeTemperatureSensorState(
                    role="extract",
                    friendly_name="temp_wywiew",
                    ieee_address=EXTRACT_IEEE,
                    topic="zigbee2mqtt/temp_wywiew",
                ),
            ),
        )

    def state(self):
        return CoreState(
            mode=VentilationMode.STOP,
            setpoints=FanSetpoints.stopped(),
            hardware_ready=True,
            zigbee=self._zigbee,
        )

    def zigbee_remove_device(self, device_id):
        self.removed.append(device_id)
        if self.remove_error is not None:
            raise RuntimeError(self.remove_error)
        return {"status": "ok", "data": {"id": device_id}}


class ZigbeeCoreConfirmationStage12Tests(unittest.TestCase):
    def test_request_does_not_remove_until_core_confirmation_is_accepted(self):
        async def scenario():
            service = FakeService()
            server = CoreServer(service, Path("/tmp/unused-zigbee-confirm.sock"), 1.0)

            requested = await server._dispatch(
                {"command": "zigbee-request-remove-device", "device_id": SUPPLY_IEEE}
            )
            self.assertTrue(requested["ok"])
            self.assertTrue(requested["confirmation_required"])
            self.assertEqual(service.removed, [])
            confirmation = requested["confirmation"]
            self.assertEqual(confirmation["device_id"], SUPPLY_IEEE)
            self.assertEqual(confirmation["friendly_name"], "temp_nawiew")
            self.assertEqual(confirmation["role"], "supply")
            self.assertTrue(confirmation["destructive"])

            state = await server._dispatch({"command": "zigbee-removal-confirmation-state"})
            self.assertEqual(
                state["confirmation"]["confirmation_id"],
                confirmation["confirmation_id"],
            )

            resolved = await server._dispatch(
                {
                    "command": "zigbee-resolve-remove-device",
                    "confirmation_id": confirmation["confirmation_id"],
                    "confirmed": True,
                }
            )
            self.assertTrue(resolved["ok"])
            self.assertTrue(resolved["confirmation"]["confirmed"])
            self.assertEqual(service.removed, [SUPPLY_IEEE])
            after = await server._dispatch({"command": "zigbee-removal-confirmation-state"})
            self.assertIsNone(after["confirmation"])

        asyncio.run(scenario())

    def test_cancel_clears_confirmation_without_device_remove(self):
        async def scenario():
            service = FakeService()
            server = CoreServer(service, Path("/tmp/unused-zigbee-cancel.sock"), 1.0)
            requested = await server._dispatch(
                {"command": "zigbee-request-remove-device", "device_id": SUPPLY_IEEE}
            )
            confirmation_id = requested["confirmation"]["confirmation_id"]
            resolved = await server._dispatch(
                {
                    "command": "zigbee-resolve-remove-device",
                    "confirmation_id": confirmation_id,
                    "confirmed": False,
                }
            )
            self.assertEqual(resolved["zigbee_management"]["status"], "cancelled")
            self.assertEqual(service.removed, [])
            after = await server._dispatch({"command": "zigbee-removal-confirmation-state"})
            self.assertIsNone(after["confirmation"])

        asyncio.run(scenario())

    def test_sleeping_battery_device_keeps_core_confirmation_with_operator_hint(self):
        async def scenario():
            service = FakeService()
            service.remove_error = (
                "Failed to remove device 'temp_nawiew' (block: false, force: false, clear cache: false) "
                "(Error: AREQ - ZDO - mgmtLeaveRsp after 10000ms)"
            )
            server = CoreServer(service, Path("/tmp/unused-zigbee-sleep.sock"), 1.0)
            requested = await server._dispatch(
                {"command": "zigbee-request-remove-device", "device_id": SUPPLY_IEEE}
            )
            confirmation_id = requested["confirmation"]["confirmation_id"]

            with self.assertRaisesRegex(RuntimeError, "Wybudź je krótkim naciśnięciem"):
                await server._dispatch(
                    {
                        "command": "zigbee-resolve-remove-device",
                        "confirmation_id": confirmation_id,
                        "confirmed": True,
                    }
                )

            pending = await server._dispatch({"command": "zigbee-removal-confirmation-state"})
            self.assertEqual(pending["confirmation"]["confirmation_id"], confirmation_id)
            self.assertIn("Wybudź je krótkim naciśnięciem", pending["confirmation"]["last_error"])
            self.assertEqual(service.removed, [SUPPLY_IEEE])

            service.remove_error = None
            retried = await server._dispatch(
                {
                    "command": "zigbee-resolve-remove-device",
                    "confirmation_id": confirmation_id,
                    "confirmed": True,
                }
            )
            self.assertTrue(retried["ok"])
            self.assertEqual(service.removed, [SUPPLY_IEEE, SUPPLY_IEEE])
            after = await server._dispatch({"command": "zigbee-removal-confirmation-state"})
            self.assertIsNone(after["confirmation"])

        asyncio.run(scenario())

    def test_coordinator_cannot_enter_removal_confirmation_flow(self):
        async def scenario():
            service = FakeService()
            server = CoreServer(service, Path("/tmp/unused-zigbee-coordinator.sock"), 1.0)
            with self.assertRaisesRegex(ValueError, "coordinator cannot be removed"):
                await server._dispatch(
                    {"command": "zigbee-request-remove-device", "device_id": COORDINATOR_IEEE}
                )
            self.assertEqual(service.removed, [])

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
