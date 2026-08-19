from __future__ import annotations

from datetime import datetime, timezone
import unittest

from ventilation_core.web.app import WebApplication
from ventilation_core.web.config import WebUiConfig
from ventilation_core.web.history_series import HistorySeriesService


class FakeHistory:
    def __init__(self, by_resolution: dict[str, list[dict]]) -> None:
        self.by_resolution = by_resolution
        self.calls: list[dict] = []

    def status(self) -> dict:
        return {"available": True}

    def query(self, **kwargs):
        self.calls.append(dict(kwargs))
        return list(self.by_resolution.get(kwargs["resolution"], []))


class FakeCore:
    def request(self, payload: dict) -> dict:
        if payload.get("command") == "status":
            return {"ok": True, "state": {}}
        return {"ok": True}


def raw_metrics(*, pm25: float | None = 12.5, supply_temp: float | None = 5.5) -> dict:
    return {
        "mode": "MANUAL",
        "setpoints": {"supply_voltage": 4.0, "extract_voltage": 5.0},
        "sensor_bus": {
            "nodes": [
                {
                    "slave_address": 1,
                    "reading": {
                        "pm1_0_ug_m3": 8.0,
                        "pm2_5_ug_m3": pm25,
                        "pm4_0_ug_m3": 14.0,
                        "pm10_0_ug_m3": 19.0,
                        "humidity_percent": 45.0,
                        "temperature_celsius": 22.2,
                        "voc_index": 88.0,
                        "nox_index": 4.0,
                    },
                },
                {
                    "slave_address": 2,
                    "reading": {
                        "pm1_0_ug_m3": 2.0,
                        "pm2_5_ug_m3": 3.0,
                        "pm4_0_ug_m3": 4.0,
                        "pm10_0_ug_m3": 5.0,
                        "humidity_percent": 40.0,
                        "temperature_celsius": 23.0,
                        "voc_index": 50.0,
                        "nox_index": 2.0,
                    },
                },
            ]
        },
        "tacho": {
            "supply": {"rpm": 1400.0, "frequency_hz": 70.0},
            "extract": {"rpm": 1200.0, "frequency_hz": 60.0},
        },
        "zigbee": {
            "devices": [
                {"role": "extract", "temperature_celsius": 18.0},
                {"role": "supply", "temperature_celsius": supply_temp},
            ]
        },
        "aero_bus": {
            "telemetry": {
                "humidity_percent": 44.0,
                "supply_temperature_celsius": 19.0,
                "extract_temperature_celsius": 24.0,
                "outdoor_temperature_celsius": 7.0,
                "fan_1_percent": 35,
                "fan_2_percent": 42,
            }
        },
    }


class HistorySeriesStage1Test(unittest.TestCase):
    def setUp(self) -> None:
        self.config = WebUiConfig(
            zone1_name="Mycie",
            zone1_sensor_address=1,
            zone2_name="Lutowanie",
            zone2_sensor_address=2,
        )
        self.now = lambda: datetime(2026, 8, 19, 20, 0, tzinfo=timezone.utc)

    def test_catalog_exposes_stable_series_and_current_safe_ranges(self) -> None:
        service = HistorySeriesService(FakeHistory({}), self.config, now=self.now)
        catalog = service.catalog()
        self.assertEqual(catalog["schema_version"], 1)
        self.assertEqual([item["id"] for item in catalog["ranges"]], ["1h", "24h", "7d"])
        ids = {item["id"] for item in catalog["series"]}
        self.assertIn("zone1.air.pm2_5", ids)
        self.assertIn("zone1.air.voc_index", ids)
        self.assertIn("zone1.fans.supply.rpm", ids)
        self.assertIn("zone1.fans.supply.setpoint_v", ids)
        self.assertIn("zone1.duct.supply.temperature", ids)
        self.assertIn("zone2.air.pm10_0", ids)
        self.assertIn("zone2.aero.supply_temperature", ids)
        self.assertIn("zone2.aero.fan2_percent", ids)

    def test_auto_resolution_uses_raw_for_hour_minute_for_day_and_15m_for_week(self) -> None:
        history = FakeHistory({"raw": [], "1m": [], "15m": []})
        service = HistorySeriesService(history, self.config, now=self.now)
        series = ["zone1.air.pm2_5"]

        self.assertEqual(service.query({"range": "1h", "series": series})["resolution"], "raw")
        self.assertEqual(service.query({"range": "24h", "series": series})["resolution"], "1m")
        self.assertEqual(service.query({"range": "7d", "series": series})["resolution"], "15m")
        self.assertEqual([call["resolution"] for call in history.calls], ["raw", "1m", "15m"])

    def test_raw_projection_uses_configured_zone_address_and_keeps_missing_point(self) -> None:
        samples = [
            {
                "captured_at": "2026-08-19T19:59:50Z",
                "metrics": raw_metrics(pm25=12.5),
            },
            {
                "captured_at": "2026-08-19T19:59:55Z",
                "metrics": raw_metrics(pm25=None),
            },
        ]
        history = FakeHistory({"raw": samples})
        service = HistorySeriesService(history, self.config, now=self.now)
        payload = service.query({"range": "1h", "series": ["zone1.air.pm2_5"]})
        series = payload["series"][0]
        self.assertEqual(series["unit"], "µg/m³")
        self.assertEqual(series["points"][0]["value"], 12.5)
        self.assertIsNone(series["points"][1]["value"])
        self.assertEqual(series["missing_points"], 1)

    def test_raw_projection_exposes_setpoint_tacho_aero_and_zigbee_role(self) -> None:
        sample = {"captured_at": "2026-08-19T19:59:55Z", "metrics": raw_metrics(supply_temp=6.25)}
        history = FakeHistory({"raw": [sample]})
        service = HistorySeriesService(history, self.config, now=self.now)
        payload = service.query(
            {
                "range": "1h",
                "series": [
                    "zone1.fans.supply.setpoint_v",
                    "zone1.fans.supply.rpm",
                    "zone1.duct.supply.temperature",
                    "zone2.aero.fan1_percent",
                ],
            }
        )
        values = {item["id"]: item["points"][0]["value"] for item in payload["series"]}
        self.assertEqual(values["zone1.fans.supply.setpoint_v"], 4.0)
        self.assertEqual(values["zone1.fans.supply.rpm"], 1400.0)
        self.assertEqual(values["zone1.duct.supply.temperature"], 6.25)
        self.assertEqual(values["zone2.aero.fan1_percent"], 35.0)

    def test_rollup_projection_returns_backend_avg_min_max_last_and_role_signal(self) -> None:
        rollup = {
            "signals": {
                "sensor_bus.nodes[1].reading.pm2_5_ug_m3": {
                    "count": 12,
                    "min": 10.0,
                    "max": 15.0,
                    "avg": 12.25,
                    "last": 14.0,
                },
                "zigbee.devices[1].temperature_celsius": {
                    "count": 11,
                    "min": 5.0,
                    "max": 7.0,
                    "avg": 6.0,
                    "last": 6.5,
                },
            },
            "states": {
                "zigbee.devices[0].role": {"count": 12, "last": "extract", "changes": 0},
                "zigbee.devices[1].role": {"count": 12, "last": "supply", "changes": 0},
            },
        }
        history = FakeHistory(
            {
                "1m": [
                    {
                        "bucket_start": "2026-08-19T19:59:00Z",
                        "sample_count": 12,
                        "rollup": rollup,
                    }
                ]
            }
        )
        service = HistorySeriesService(history, self.config, now=self.now)
        payload = service.query(
            {
                "range": "24h",
                "series": ["zone1.air.pm2_5", "zone1.duct.supply.temperature"],
            }
        )
        pm = payload["series"][0]["points"][0]
        duct = payload["series"][1]["points"][0]
        self.assertEqual(pm["avg"], 12.25)
        self.assertEqual(pm["min"], 10.0)
        self.assertEqual(pm["max"], 15.0)
        self.assertEqual(pm["last"], 14.0)
        self.assertEqual(pm["count"], 12)
        self.assertEqual(pm["sample_count"], 12)
        self.assertEqual(duct["avg"], 6.0)
        self.assertEqual(duct["count"], 11)

    def test_rejects_unknown_series_duplicate_series_and_oversized_custom_range(self) -> None:
        service = HistorySeriesService(FakeHistory({}), self.config, now=self.now)
        with self.assertRaisesRegex(ValueError, "unknown history series"):
            service.query({"range": "1h", "series": ["zone9.unknown"]})
        with self.assertRaisesRegex(ValueError, "must be unique"):
            service.query({"range": "1h", "series": ["zone1.air.pm2_5", "zone1.air.pm2_5"]})
        with self.assertRaisesRegex(ValueError, "too large"):
            service.query(
                {
                    "start_at": "2026-07-01T00:00:00Z",
                    "end_at": "2026-08-19T20:00:00Z",
                    "series": ["zone1.air.pm2_5"],
                    "resolution": "15m",
                }
            )

    def test_web_application_exposes_catalog_and_series_query(self) -> None:
        history = FakeHistory({"raw": []})
        app = WebApplication(FakeCore(), config=self.config, history=history)
        catalog = app.handle("GET", "/api/v1/history/series")
        self.assertEqual(catalog.status, 200)
        self.assertTrue(catalog.payload["ok"])
        query = app.handle(
            "POST",
            "/api/v1/history/series/query",
            {"range": "1h", "series": ["zone1.air.pm2_5"]},
        )
        self.assertEqual(query.status, 200)
        self.assertEqual(query.payload["history"]["resolution"], "raw")

    def test_web_application_reports_unconfigured_series_api(self) -> None:
        app = WebApplication(FakeCore(), config=self.config, history=None)
        response = app.handle("GET", "/api/v1/history/series")
        self.assertEqual(response.status, 503)
        self.assertFalse(response.payload["ok"])


if __name__ == "__main__":
    unittest.main()
