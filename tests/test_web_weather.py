import tempfile
import unittest
from pathlib import Path

from ventilation_core.weather.cache import WeatherCache
from ventilation_core.web.weather import FileWeatherProvider


class WebWeatherTest(unittest.TestCase):
    def test_missing_snapshot_is_informational(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = FileWeatherProvider(Path(tmp) / "weather.json")
            snapshot = provider.get_snapshot()

        self.assertFalse(snapshot["available"])
        self.assertTrue(snapshot["configured"])
        self.assertEqual(snapshot["source"], "local-cache")

    def test_web_reads_local_snapshot_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weather.json"
            WeatherCache(path).save(
                {
                    "available": True,
                    "configured": True,
                    "provider": "met-no",
                    "attribution": "MET Norway",
                    "location": "Warsztat",
                    "temperature_celsius": 24.2,
                    "condition": "Częściowe zachmurzenie",
                    "icon": "⛅",
                    "precipitation_amount_mm": 0.4,
                    "wind_speed_kmh": 12.6,
                    "observed_at": "2026-08-13T11:00:00Z",
                }
            )
            snapshot = FileWeatherProvider(path).get_snapshot()

        self.assertTrue(snapshot["available"])
        self.assertTrue(snapshot["cached"])
        self.assertEqual(snapshot["source"], "local-cache")
        self.assertEqual(snapshot["temperature_celsius"], 24.2)
        self.assertEqual(snapshot["location"], "Warsztat")
        self.assertIsNotNone(snapshot["fetched_at"])


if __name__ == "__main__":
    unittest.main()
