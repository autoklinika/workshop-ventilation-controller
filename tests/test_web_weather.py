import unittest

from ventilation_core.web.weather import MetNoWeatherProvider, WeatherConfig, symbol_presentation


class FakeWeather(MetNoWeatherProvider):
    def __init__(self, config, clock):
        super().__init__(config, clock=clock)
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


class WebWeatherTest(unittest.TestCase):
    def test_unconfigured_weather_never_calls_provider(self):
        provider = FakeWeather(WeatherConfig(), lambda: 0.0)
        snapshot = provider.get_snapshot()
        self.assertFalse(snapshot["available"])
        self.assertFalse(snapshot["configured"])
        self.assertEqual(provider.calls, [])

    def test_forecast_and_cache(self):
        now = [100.0]
        provider = FakeWeather(
            WeatherConfig(
                latitude=52.4064,
                longitude=16.9252,
                label="Poznań",
                user_agent="WorkshopVentilation/1.0 contact@example.com",
                cache_seconds=3600,
            ),
            lambda: now[0],
        )
        first = provider.get_snapshot()
        second = provider.get_snapshot()

        self.assertTrue(first["available"])
        self.assertFalse(first["cached"])
        self.assertEqual(first["temperature_celsius"], 24.2)
        self.assertEqual(first["precipitation_amount_mm"], 0.4)
        self.assertAlmostEqual(first["wind_speed_kmh"], 12.6)
        self.assertEqual(first["location"], "Poznań")
        self.assertEqual(first["attribution"], "MET Norway")
        self.assertTrue(second["cached"])
        self.assertEqual(len(provider.calls), 1)

        now[0] += 3601
        provider.get_snapshot()
        self.assertEqual(len(provider.calls), 2)

    def test_symbol_presentation(self):
        self.assertEqual(symbol_presentation("clearsky_day"), ("Bezchmurnie", "☀"))
        self.assertEqual(symbol_presentation("rain"), ("Deszcz", "🌧"))
        self.assertEqual(symbol_presentation("heavyrainandthunder"), ("Burza", "⛈"))


if __name__ == "__main__":
    unittest.main()
