import unittest

from ventilation_core.web.weather import OpenMeteoWeatherProvider, WeatherConfig, weather_code_presentation


class FakeWeather(OpenMeteoWeatherProvider):
    def __init__(self, config, clock):
        super().__init__(config, clock=clock)
        self.calls = []

    def _get_json(self, endpoint, params):
        self.calls.append((endpoint, params))
        if "geocoding" in endpoint:
            return {
                "results": [
                    {
                        "name": "Poznań",
                        "admin1": "Wielkopolskie",
                        "country": "Polska",
                        "latitude": 52.4064,
                        "longitude": 16.9252,
                    }
                ]
            }
        return {
            "current": {
                "time": "2026-08-13T13:30",
                "temperature_2m": 24.2,
                "apparent_temperature": 24.7,
                "weather_code": 2,
                "wind_speed_10m": 13.4,
                "is_day": 1,
            },
            "hourly": {
                "time": ["2026-08-13T13:00", "2026-08-13T14:00"],
                "precipitation_probability": [20, 40],
            },
        }


class WebWeatherTest(unittest.TestCase):
    def test_unconfigured_weather_never_calls_provider(self):
        provider = FakeWeather(WeatherConfig(location=""), lambda: 0.0)
        snapshot = provider.get_snapshot()
        self.assertFalse(snapshot["available"])
        self.assertFalse(snapshot["configured"])
        self.assertEqual(provider.calls, [])

    def test_geocoding_forecast_and_cache(self):
        now = [100.0]
        provider = FakeWeather(WeatherConfig(location="Poznań", cache_seconds=900), lambda: now[0])
        first = provider.get_snapshot()
        second = provider.get_snapshot()

        self.assertTrue(first["available"])
        self.assertFalse(first["cached"])
        self.assertEqual(first["temperature_celsius"], 24.2)
        self.assertEqual(first["precipitation_probability_percent"], 20)
        self.assertEqual(first["wind_speed_kmh"], 13.4)
        self.assertEqual(first["location"], "Poznań, Wielkopolskie")
        self.assertTrue(second["cached"])
        self.assertEqual(len(provider.calls), 2)

        now[0] += 901
        provider.get_snapshot()
        self.assertEqual(len(provider.calls), 3)

    def test_weather_code_presentation(self):
        self.assertEqual(weather_code_presentation(0, True), ("Bezchmurnie", "☀"))
        self.assertEqual(weather_code_presentation(63, True), ("Deszcz", "🌧"))
        self.assertEqual(weather_code_presentation(95, False), ("Burza", "⛈"))


if __name__ == "__main__":
    unittest.main()
