from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ventilation_core.application.zigbee_measurements import (
    DEFAULT_ZIGBEE_STALE_SECONDS,
    normalize_zigbee_temperature,
)
from ventilation_core.domain.zigbee import ZigbeeMqttState, ZigbeeTemperatureSensorState


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def state(
    *,
    connected: bool = True,
    bridge_online: bool | None = True,
    available: bool | None = True,
    temperature: float | None = 5.0,
    age_seconds: float = 60.0,
    role: str = "supply",
) -> ZigbeeMqttState:
    timestamp = (NOW - timedelta(seconds=age_seconds)).isoformat()
    return ZigbeeMqttState(
        broker_host="127.0.0.1",
        broker_port=1883,
        base_topic="zigbee2mqtt",
        running=True,
        connected=connected,
        bridge_online=bridge_online,
        devices=(
            ZigbeeTemperatureSensorState(
                role=role,
                friendly_name="temp_nawiew",
                ieee_address="0xabc",
                topic="zigbee2mqtt/temp_nawiew",
                available=available,
                temperature_celsius=temperature,
                last_seen=timestamp,
                last_message_at=timestamp,
                messages=1,
            ),
        ),
    )


class ZigbeeTemperatureNormalizationTest(unittest.TestCase):
    def test_fresh_role_measurement_is_usable(self) -> None:
        result = normalize_zigbee_temperature(state(), "supply", now_utc=NOW)
        self.assertTrue(result.usable)
        self.assertFalse(result.stale)
        self.assertEqual(result.temperature_celsius, 5.0)
        self.assertAlmostEqual(result.age_seconds or 0.0, 60.0)
        self.assertEqual(result.reason, "OK")

    def test_stale_measurement_is_preserved_for_diagnostics_but_not_usable(self) -> None:
        result = normalize_zigbee_temperature(
            state(age_seconds=DEFAULT_ZIGBEE_STALE_SECONDS + 1),
            "supply",
            now_utc=NOW,
        )
        self.assertFalse(result.usable)
        self.assertTrue(result.stale)
        self.assertEqual(result.temperature_celsius, 5.0)
        self.assertEqual(result.reason, "TEMPERATURE_STALE")

    def test_offline_device_is_not_usable(self) -> None:
        result = normalize_zigbee_temperature(
            state(available=False),
            "supply",
            now_utc=NOW,
        )
        self.assertFalse(result.usable)
        self.assertEqual(result.reason, "ZIGBEE_DEVICE_OFFLINE")

    def test_disconnected_transport_is_not_usable(self) -> None:
        result = normalize_zigbee_temperature(
            state(connected=False),
            "supply",
            now_utc=NOW,
        )
        self.assertFalse(result.usable)
        self.assertEqual(result.reason, "ZIGBEE_MQTT_DISCONNECTED")

    def test_bridge_offline_is_not_usable(self) -> None:
        result = normalize_zigbee_temperature(
            state(bridge_online=False),
            "supply",
            now_utc=NOW,
        )
        self.assertFalse(result.usable)
        self.assertEqual(result.reason, "ZIGBEE_BRIDGE_OFFLINE")

    def test_missing_role_is_explicit(self) -> None:
        result = normalize_zigbee_temperature(
            state(role="extract"),
            "supply",
            now_utc=NOW,
        )
        self.assertFalse(result.usable)
        self.assertIsNone(result.temperature_celsius)
        self.assertEqual(result.reason, "ZIGBEE_ROLE_UNASSIGNED")

    def test_missing_temperature_is_not_usable(self) -> None:
        result = normalize_zigbee_temperature(
            state(temperature=None),
            "supply",
            now_utc=NOW,
        )
        self.assertFalse(result.usable)
        self.assertEqual(result.reason, "TEMPERATURE_UNAVAILABLE")

    def test_last_seen_has_precedence_over_recent_retained_message_time(self) -> None:
        old = (NOW - timedelta(seconds=DEFAULT_ZIGBEE_STALE_SECONDS + 10)).isoformat()
        recent = NOW.isoformat()
        zigbee = ZigbeeMqttState(
            broker_host="127.0.0.1",
            broker_port=1883,
            base_topic="zigbee2mqtt",
            running=True,
            connected=True,
            bridge_online=True,
            devices=(
                ZigbeeTemperatureSensorState(
                    role="supply",
                    friendly_name="temp_nawiew",
                    ieee_address="0xabc",
                    topic="zigbee2mqtt/temp_nawiew",
                    available=True,
                    temperature_celsius=4.0,
                    last_seen=old,
                    last_message_at=recent,
                    messages=1,
                ),
            ),
        )
        result = normalize_zigbee_temperature(zigbee, "supply", now_utc=NOW)
        self.assertFalse(result.usable)
        self.assertTrue(result.stale)
        self.assertEqual(result.source_timestamp, old)

    def test_naive_clock_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            normalize_zigbee_temperature(
                state(),
                "supply",
                now_utc=datetime(2026, 8, 27, 12, 0),
            )


if __name__ == "__main__":
    unittest.main()
