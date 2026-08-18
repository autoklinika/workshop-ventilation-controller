from __future__ import annotations

from datetime import datetime, timezone
import unittest

from ventilation_core.telemetry.rollup import RollupSample, floor_utc, summarize_metrics


class TelemetryRollupTest(unittest.TestCase):
    def test_numeric_state_and_sensor_node_rollups_are_stable(self) -> None:
        samples = [
            RollupSample(
                captured_at="2026-08-17T10:00:05+00:00",
                metrics={
                    "mode": "STOP",
                    "hardware_ready": True,
                    "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
                    "active_alarms": [],
                    "sensor_bus": {
                        "nodes": [
                            {
                                "slave_address": 2,
                                "online": True,
                                "reading": {"pm2_5_ug_m3": 20.0},
                            },
                            {
                                "slave_address": 1,
                                "online": True,
                                "reading": {"pm2_5_ug_m3": 10.0},
                            },
                        ]
                    },
                },
            ),
            RollupSample(
                captured_at="2026-08-17T10:00:25+00:00",
                metrics={
                    "mode": "MANUAL",
                    "hardware_ready": True,
                    "setpoints": {"supply_voltage": 4.0, "extract_voltage": 5.0},
                    "active_alarms": [{"code": "TEST"}],
                    "sensor_bus": {
                        "nodes": [
                            {
                                "slave_address": 1,
                                "online": False,
                                "reading": {"pm2_5_ug_m3": 14.0},
                            },
                            {
                                "slave_address": 2,
                                "online": True,
                                "reading": {"pm2_5_ug_m3": 24.0},
                            },
                        ]
                    },
                },
            ),
        ]

        result = summarize_metrics(samples)

        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["first_captured_at"], "2026-08-17T10:00:05+00:00")
        self.assertEqual(result["last_captured_at"], "2026-08-17T10:00:25+00:00")

        supply = result["signals"]["setpoints.supply_voltage"]
        self.assertEqual(supply["min"], 0.0)
        self.assertEqual(supply["max"], 4.0)
        self.assertEqual(supply["avg"], 2.0)
        self.assertEqual(supply["last"], 4.0)

        node1_pm = result["signals"]["sensor_bus.nodes[1].reading.pm2_5_ug_m3"]
        self.assertEqual(node1_pm["avg"], 12.0)
        node2_pm = result["signals"]["sensor_bus.nodes[2].reading.pm2_5_ug_m3"]
        self.assertEqual(node2_pm["avg"], 22.0)

        node1_online = result["states"]["sensor_bus.nodes[1].online"]
        self.assertEqual(node1_online["changes"], 1)
        self.assertEqual(node1_online["true_count"], 1)
        self.assertFalse(node1_online["last"])

        mode = result["states"]["mode"]
        self.assertEqual(mode["changes"], 1)
        self.assertEqual(mode["last"], "MANUAL")

        alarm_count = result["signals"]["active_alarms.count"]
        self.assertEqual(alarm_count["min"], 0.0)
        self.assertEqual(alarm_count["max"], 1.0)
        self.assertEqual(alarm_count["last"], 1.0)

    def test_rollup_requires_samples(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one sample"):
            summarize_metrics([])

    def test_floor_utc_uses_epoch_aligned_buckets(self) -> None:
        value = datetime(2026, 8, 17, 12, 34, 56, tzinfo=timezone.utc)
        self.assertEqual(
            floor_utc(value, 60),
            datetime(2026, 8, 17, 12, 34, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            floor_utc(value, 900),
            datetime(2026, 8, 17, 12, 30, 0, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
