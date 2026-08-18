import unittest
from datetime import datetime, timezone

from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.zigbee_service import ZigbeeAlertingVentilationService
from ventilation_core.domain.models import AlarmCode, FanSetpoints
from ventilation_core.domain.policy import FanSetpointPolicy
from ventilation_core.domain.zigbee import ZigbeeInventoryDevice, ZigbeeMqttState, ZigbeeTemperatureSensorState
from ventilation_core.infrastructure.zigbee_reliable_monitor import parse_availability_payload


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

    def state(self):
        return self.current_state

    def health_check(self):
        return None

    def close(self):
        return None


def make_state(*, last_seen, last_message_at):
    devices = (
        ZigbeeTemperatureSensorState(
            role="supply",
            friendly_name="temp_nawiew",
            ieee_address="0xa4c13810e66fffff",
            topic="zigbee2mqtt/temp_nawiew",
            available=True,
            temperature_celsius=25.0,
            battery_percent=100.0,
            linkquality=80,
            last_seen=last_seen,
            last_message_at=last_message_at,
            messages=1,
        ),
    )
    inventory = (
        ZigbeeInventoryDevice(
            ieee_address="0xa4c13810e66fffff",
            friendly_name="temp_nawiew",
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
        connected=True,
        bridge_online=True,
        inventory_updated_at=datetime.now(timezone.utc).isoformat(),
        inventory=inventory,
        devices=devices,
    )


class ZigbeeReliabilityStage10Tests(unittest.TestCase):
    def test_current_json_availability_payload_is_supported(self):
        self.assertTrue(parse_availability_payload(b'{"state":"online"}'))
        self.assertFalse(parse_availability_payload(b'{"state":"offline"}'))

    def test_legacy_plaintext_availability_remains_supported(self):
        self.assertTrue(parse_availability_payload(b"online"))
        self.assertFalse(parse_availability_payload(b"offline"))

    def test_invalid_availability_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_availability_payload(b'{"state":"unknown"}')

    def test_retained_delivery_does_not_make_old_measurement_fresh(self):
        now = datetime.now(timezone.utc).isoformat()
        state = make_state(last_seen="2020-01-01T00:00:00+00:00", last_message_at=now)
        service = ZigbeeAlertingVentilationService(
            actuator=FakeActuator(),
            policy=FanSetpointPolicy(1.0, 10.0),
            zigbee=FakeZigbee(state),
            alert_registry=AlertRegistry(MemoryAlertStore()),
        )
        result = service.health_check()
        self.assertIn(
            AlarmCode.ZIGBEE_DEVICE_DATA_STALE,
            {alert.code for alert in result.active_alarms},
        )
        service.close()

    def test_fresh_device_last_seen_wins_over_old_core_receive_time(self):
        now = datetime.now(timezone.utc).isoformat()
        state = make_state(last_seen=now, last_message_at="2020-01-01T00:00:00+00:00")
        service = ZigbeeAlertingVentilationService(
            actuator=FakeActuator(),
            policy=FanSetpointPolicy(1.0, 10.0),
            zigbee=FakeZigbee(state),
            alert_registry=AlertRegistry(MemoryAlertStore()),
        )
        result = service.health_check()
        self.assertNotIn(
            AlarmCode.ZIGBEE_DEVICE_DATA_STALE,
            {alert.code for alert in result.active_alarms},
        )
        service.close()


if __name__ == "__main__":
    unittest.main()
