from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import urlopen


GEOCODING_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"


class WeatherError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeatherConfig:
    location: str = ""
    cache_seconds: float = 900.0
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.cache_seconds <= 0:
            raise ValueError("weather cache_seconds must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("weather timeout_seconds must be positive")


class OpenMeteoWeatherProvider:
    """Informational weather provider isolated from ventilation-core.

    Geocoding is resolved once per process. Forecast snapshots are cached so browser
    polling cannot turn into repeated Internet requests. Weather failures never
    affect actuator state or ventilation-core availability.
    """

    def __init__(
        self,
        config: WeatherConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._coordinates: dict[str, Any] | None = None
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_expires_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._config.location.strip())

    def get_snapshot(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "available": False,
                "configured": False,
                "error": "weather location is not configured",
            }

        now = self._clock()
        if self._snapshot is not None and now < self._snapshot_expires_at:
            return {**self._snapshot, "cached": True}

        coordinates = self._coordinates or self._resolve_location()
        self._coordinates = coordinates
        snapshot = self._fetch_forecast(coordinates)
        self._snapshot = snapshot
        self._snapshot_expires_at = now + self._config.cache_seconds
        return {**snapshot, "cached": False}

    def _resolve_location(self) -> dict[str, Any]:
        payload = self._get_json(
            GEOCODING_ENDPOINT,
            {
                "name": self._config.location.strip(),
                "count": 1,
                "language": "pl",
                "format": "json",
            },
        )
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise WeatherError(f"weather location not found: {self._config.location.strip()}")
        result = results[0]
        latitude = result.get("latitude")
        longitude = result.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            raise WeatherError("geocoding response does not contain coordinates")
        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "name": str(result.get("name") or self._config.location.strip()),
            "admin1": str(result.get("admin1") or ""),
            "country": str(result.get("country") or ""),
        }

    def _fetch_forecast(self, location: dict[str, Any]) -> dict[str, Any]:
        payload = self._get_json(
            FORECAST_ENDPOINT,
            {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
                "hourly": "precipitation_probability",
                "forecast_days": 1,
                "timezone": "auto",
            },
        )
        current = payload.get("current")
        if not isinstance(current, dict):
            raise WeatherError("forecast response does not contain current weather")

        temperature = self._number(current.get("temperature_2m"), "temperature_2m")
        apparent = self._number(current.get("apparent_temperature"), "apparent_temperature")
        wind = self._number(current.get("wind_speed_10m"), "wind_speed_10m")
        weather_code = int(self._number(current.get("weather_code"), "weather_code"))
        current_time = current.get("time")
        if not isinstance(current_time, str) or not current_time:
            raise WeatherError("forecast response does not contain current time")

        precipitation_probability = self._nearest_precipitation_probability(
            payload.get("hourly"), current_time
        )
        condition, icon = weather_code_presentation(
            weather_code,
            bool(current.get("is_day", 1)),
        )

        location_label = location["name"]
        if location.get("admin1") and location["admin1"] != location_label:
            location_label = f"{location_label}, {location['admin1']}"

        return {
            "available": True,
            "configured": True,
            "provider": "open-meteo",
            "location": location_label,
            "temperature_celsius": temperature,
            "apparent_temperature_celsius": apparent,
            "condition": condition,
            "icon": icon,
            "weather_code": weather_code,
            "precipitation_probability_percent": precipitation_probability,
            "wind_speed_kmh": wind,
            "observed_at": current_time,
        }

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{endpoint}?{urlencode(params)}"
        try:
            with urlopen(url, timeout=self._config.timeout_seconds) as response:
                raw = response.read()
        except OSError as exc:
            raise WeatherError(f"weather provider unavailable: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WeatherError("weather provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WeatherError("weather provider returned unexpected payload")
        if payload.get("error") is True:
            raise WeatherError(str(payload.get("reason") or "weather provider error"))
        return payload

    @staticmethod
    def _number(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise WeatherError(f"forecast field {name} is missing")
        return float(value)

    @staticmethod
    def _nearest_precipitation_probability(hourly: Any, current_time: str) -> int | None:
        if not isinstance(hourly, dict):
            return None
        times = hourly.get("time")
        values = hourly.get("precipitation_probability")
        if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values):
            return None
        try:
            current_dt = datetime.fromisoformat(current_time)
        except ValueError:
            return None

        nearest: tuple[float, int] | None = None
        for time_value, probability in zip(times, values):
            if not isinstance(time_value, str) or isinstance(probability, bool) or not isinstance(
                probability, (int, float)
            ):
                continue
            try:
                sample_dt = datetime.fromisoformat(time_value)
            except ValueError:
                continue
            distance = abs((sample_dt - current_dt).total_seconds())
            candidate = (distance, int(round(float(probability))))
            if nearest is None or candidate[0] < nearest[0]:
                nearest = candidate
        return nearest[1] if nearest is not None else None


def weather_code_presentation(code: int, is_day: bool) -> tuple[str, str]:
    if code == 0:
        return ("Bezchmurnie", "☀" if is_day else "☾")
    if code in (1, 2):
        return ("Małe zachmurzenie", "⛅" if is_day else "☁")
    if code == 3:
        return ("Pochmurno", "☁")
    if code in (45, 48):
        return ("Mgła", "≋")
    if code in (51, 53, 55, 56, 57):
        return ("Mżawka", "🌦")
    if code in (61, 63, 65, 66, 67):
        return ("Deszcz", "🌧")
    if code in (71, 73, 75, 77):
        return ("Śnieg", "❄")
    if code in (80, 81, 82):
        return ("Przelotne opady", "🌦")
    if code in (85, 86):
        return ("Przelotny śnieg", "🌨")
    if code in (95, 96, 99):
        return ("Burza", "⛈")
    return ("Warunki zmienne", "◌")
