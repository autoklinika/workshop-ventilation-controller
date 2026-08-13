from __future__ import annotations

import gzip
import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FORECAST_ENDPOINT = "https://api.met.no/weatherapi/locationforecast/2.0/compact"


class WeatherError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeatherConfig:
    latitude: float | None = None
    longitude: float | None = None
    label: str = ""
    user_agent: str = ""
    cache_seconds: float = 3600.0
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.latitude is not None and not -90.0 <= self.latitude <= 90.0:
            raise ValueError("weather latitude must be within -90..90")
        if self.longitude is not None and not -180.0 <= self.longitude <= 180.0:
            raise ValueError("weather longitude must be within -180..180")
        if self.cache_seconds <= 0:
            raise ValueError("weather cache_seconds must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("weather timeout_seconds must be positive")


class MetNoWeatherProvider:
    """Read-only weather provider isolated from ventilation-core.

    The browser talks only to the local Web UI. Forecast data are cached locally;
    provider/network failures never affect actuator state or core availability.
    """

    def __init__(
        self,
        config: WeatherConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_expires_at = 0.0

    @property
    def configured(self) -> bool:
        return (
            self._config.latitude is not None
            and self._config.longitude is not None
            and bool(self._config.user_agent.strip())
        )

    def get_snapshot(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "available": False,
                "configured": False,
                "error": "weather coordinates or identifying user-agent are not configured",
            }

        now = self._clock()
        if self._snapshot is not None and now < self._snapshot_expires_at:
            return {**self._snapshot, "cached": True}

        snapshot = self._fetch_forecast()
        self._snapshot = snapshot
        self._snapshot_expires_at = now + self._config.cache_seconds
        return {**snapshot, "cached": False}

    def _fetch_forecast(self) -> dict[str, Any]:
        payload = self._get_json(
            {
                "lat": f"{self._config.latitude:.4f}",
                "lon": f"{self._config.longitude:.4f}",
            }
        )
        properties = payload.get("properties")
        timeseries = properties.get("timeseries") if isinstance(properties, dict) else None
        if not isinstance(timeseries, list) or not timeseries:
            raise WeatherError("forecast response does not contain timeseries")

        sample = timeseries[0]
        data = sample.get("data") if isinstance(sample, dict) else None
        instant = data.get("instant") if isinstance(data, dict) else None
        details = instant.get("details") if isinstance(instant, dict) else None
        if not isinstance(details, dict):
            raise WeatherError("forecast response does not contain instant details")

        temperature = self._number(details.get("air_temperature"), "air_temperature")
        wind = self._number(details.get("wind_speed"), "wind_speed")
        wind_kmh = wind * 3.6

        period = None
        for key in ("next_1_hours", "next_6_hours", "next_12_hours"):
            candidate = data.get(key) if isinstance(data, dict) else None
            if isinstance(candidate, dict):
                period = candidate
                break

        precipitation_mm: float | None = None
        symbol_code = ""
        if period is not None:
            period_details = period.get("details")
            if isinstance(period_details, dict):
                value = period_details.get("precipitation_amount")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    precipitation_mm = float(value)
            summary = period.get("summary")
            if isinstance(summary, dict) and isinstance(summary.get("symbol_code"), str):
                symbol_code = summary["symbol_code"]

        condition, icon = symbol_presentation(symbol_code)
        observed_at = sample.get("time") if isinstance(sample, dict) else None

        return {
            "available": True,
            "configured": True,
            "provider": "met-no",
            "attribution": "MET Norway",
            "location": self._config.label.strip(),
            "temperature_celsius": temperature,
            "condition": condition,
            "icon": icon,
            "symbol_code": symbol_code,
            "precipitation_amount_mm": precipitation_mm,
            "wind_speed_kmh": wind_kmh,
            "observed_at": observed_at,
        }

    def _get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{FORECAST_ENDPOINT}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "User-Agent": self._config.user_agent.strip(),
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
        )
        try:
            with urlopen(request, timeout=self._config.timeout_seconds) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
        except OSError as exc:
            raise WeatherError(f"weather provider unavailable: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WeatherError("weather provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WeatherError("weather provider returned unexpected payload")
        return payload

    @staticmethod
    def _number(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise WeatherError(f"forecast field {name} is missing")
        return float(value)


def symbol_presentation(symbol_code: str) -> tuple[str, str]:
    code = symbol_code.lower()
    if "thunder" in code:
        return ("Burza", "⛈")
    if "snow" in code:
        return ("Śnieg", "❄")
    if "sleet" in code:
        return ("Deszcz ze śniegiem", "🌨")
    if "rain" in code:
        return ("Deszcz", "🌧")
    if "fog" in code:
        return ("Mgła", "≋")
    if "partlycloudy" in code:
        return ("Częściowe zachmurzenie", "⛅")
    if "cloudy" in code or "fair" in code:
        return ("Zachmurzenie", "☁")
    if "clearsky" in code:
        return ("Bezchmurnie", "☀" if not code.endswith("_night") else "☾")
    return ("Warunki zmienne", "◌")
