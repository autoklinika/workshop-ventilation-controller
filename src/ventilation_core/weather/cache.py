from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any


CACHE_SCHEMA_VERSION = 1


class WeatherCache:
    """Atomic local cache shared by the weather service and read-only clients."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read weather cache {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
            raise RuntimeError("weather cache has an unsupported format")
        weather = payload.get("weather")
        if not isinstance(weather, dict):
            raise RuntimeError("weather cache does not contain a weather object")
        return payload

    def load_snapshot(self) -> dict[str, Any] | None:
        payload = self.load()
        if payload is None:
            return None
        weather = dict(payload["weather"])
        weather["cached"] = True
        weather["fetched_at"] = payload.get("fetched_at")
        return weather

    def save(self, weather: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "weather": weather,
        }
        encoded = json.dumps(
            envelope,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.chmod(temporary_path, 0o640)
            os.replace(temporary_path, self.path)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise RuntimeError(f"Cannot write weather cache {self.path}: {exc}") from exc
