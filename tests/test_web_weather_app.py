import unittest

from ventilation_core.web.app import WebApplication
from ventilation_core.web.weather import WeatherError


class FakeCore:
    def __init__(self):
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return {"ok": True, "state": {"mode": "STOP"}}


class FakeWeather:
    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot or {"available": True, "temperature_celsius": 20.0}
        self.error = error
        self.calls = 0

    def get_snapshot(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.snapshot


class WebWeatherApplicationTest(unittest.TestCase):
    def test_weather_endpoint_does_not_touch_core(self):
        core = FakeCore()
        weather = FakeWeather({"available": True, "temperature_celsius": 21.5})
        response = WebApplication(core, weather=weather).handle("GET", "/api/v1/weather")
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["weather"]["available"])
        self.assertEqual(core.requests, [])
        self.assertEqual(weather.calls, 1)

    def test_weather_failure_is_informational_not_service_failure(self):
        core = FakeCore()
        weather = FakeWeather(error=WeatherError("offline"))
        response = WebApplication(core, weather=weather).handle("GET", "/api/v1/weather")
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["ok"])
        self.assertFalse(response.payload["weather"]["available"])
        self.assertEqual(core.requests, [])

    def test_missing_provider_returns_unconfigured_state(self):
        core = FakeCore()
        response = WebApplication(core).handle("GET", "/api/v1/weather")
        self.assertEqual(response.status, 200)
        self.assertFalse(response.payload["weather"]["configured"])
        self.assertEqual(core.requests, [])


if __name__ == "__main__":
    unittest.main()
