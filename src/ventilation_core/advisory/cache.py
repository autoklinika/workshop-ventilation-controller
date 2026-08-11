from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any


class AdvisoryCache:
    """Small local cache for the newest operator-facing AI advisory report."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read AI advisory cache {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("cache_schema_version") != 1:
            raise RuntimeError("AI advisory cache has an unsupported format")
        report = payload.get("report")
        if not isinstance(report, dict):
            raise RuntimeError("AI advisory cache does not contain a report object")
        return payload

    def current_analysis_id(self) -> str | None:
        payload = self.load()
        if payload is None:
            return None
        analysis_id = payload["report"].get("analysis_id")
        return analysis_id if isinstance(analysis_id, str) else None

    def save(self, report: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "cache_schema_version": 1,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "report": report,
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
            raise RuntimeError(f"Cannot write AI advisory cache {self.path}: {exc}") from exc
