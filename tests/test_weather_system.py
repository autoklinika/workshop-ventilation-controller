import tempfile
import unittest
from pathlib import Path

from ventilation_core.weather.agent import WeatherAgent
from ventilation_core.weather.cache import WeatherCache
from ventilation_core.weather.provider import MetNoWeatherClient, WeatherConfig, symbol_presentation


class FakeMetNoWeatherClient(MetNoWeatherClient):
    def __init__(self, config):
        super().__init__(config)
        self.calls = []

    def _get_json(self, params):
        self.calls.append(params)
        return {
            "properties": {
                "timeseries": [
                    {
                        "time": "2026-08-13T11:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 24.2,
                                    "wind_speed": 3.5,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "partlycloudy_day"},
                                "details": {"precipitation_amount": 0.4},
                            },
                        },
                    }
                ]
            }
        }


class WeatherSystemTest(unittest.TestCase):
    def test_provider_builds_snapshot(self):
        client = FakeMetNoWeatherClient(
            WeatherConfig(
                latitude=52.4064,
                longitude=16.9252,
                label="Warsztat",
                user_agent="WorkshopVentilation/1.0 contact@example.com",
            )
        )

        snapshot = client.fetch_snapshot()

        self.assertTrue(snapshot["available"])
        self.assertTrue(snapshot["configured"])
        self.assertEqual(snapshot["provider"], "met-no")
        self.assertEqual(snapshot["location"], "Warsztat")
        self.assertEqual(snapshot["temperature_celsius"], 24.2)
        self.assertEqual(snapshot["precipitation_amount_mm"], 0.4)
        self.assertAlmostEqual(snapshot["wind_speed_kmh"], 12.6)
        self.assertEqual(client.calls, [{"lat": "52.4064", "lon": "16.9252"}])

    def test_agent_writes_snapshot_to_local_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weather.json"
            client = FakeMetNoWeatherClient(
                WeatherConfig(
                    latitude=52.4064,
                    longitude=16.9252,
                    label="Warsztat",
                    user_agent="WorkshopVentilation/1.0 contact@example.com",
                )
            )
            agent = WeatherAgent(
                client=client,
                cache=WeatherCache(path),
                poll_interval_seconds=3600,
            )
            agent.fetch_once()
            cached = WeatherCache(path).load_snapshot()

        self.assertIsNotNone(cached)
        self.assertTrue(cached["available"])
        self.assertTrue(cached["cached"])
        self.assertEqual(cached["location"], "Warsztat")

    def test_symbol_presentation(self):
        self.assertEqual(symbol_presentation("clearsky_day"), ("Bezchmurnie", "☀"))
        self.assertEqual(symbol_presentation("rain"), ("Deszcz", "🌧"))
        self.assertEqual(symbol_presentation("heavyrainandthunder"), ("Burza", "⛈"))


if __name__ == "__main__":
    unittest.main()
