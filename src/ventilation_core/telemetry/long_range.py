from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from .store import TelemetryStore, _parse_aware_iso


class LongRangeTelemetryStore(TelemetryStore):
    """Telemetry store extension with persistent long-range rollups.

    RAW samples remain the source of truth for all rollup resolutions. Raw pruning
    is allowed only after every configured rollup has processed the candidate time
    range, so adding long-range history cannot silently create holes.

    Retention is deliberately tiered instead of keeping every 5-second sample for
    years. The CM5 therefore retains fine detail for recent periods and progressively
    coarser history for multi-year inspection without excessive eMMC growth.
    """

    QUARTER_RETENTION_DAYS = 1095  # 3 years minimum at 15-minute resolution
    HOURLY_RETENTION_DAYS = 1825  # 5 years
    DAILY_RETENTION_DAYS = 3650  # 10 years

    ROLLUPS = {
        **TelemetryStore.ROLLUPS,
        "1h": ("telemetry_rollup_1h", 60 * 60),
        "1d": ("telemetry_rollup_1d", 24 * 60 * 60),
    }

    def initialize(self) -> None:
        super().initialize()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_rollup_1h (
                    bucket_start TEXT PRIMARY KEY,
                    bucket_end TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    rollup_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telemetry_rollup_1d (
                    bucket_start TEXT PRIMARY KEY,
                    bucket_end TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    rollup_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def prune_history(
        self,
        *,
        raw_retention_days: int,
        minute_retention_days: int,
        quarter_retention_days: int,
        now: datetime | None = None,
    ) -> dict[str, int]:
        # Existing service arguments remain valid, but H4 guarantees that the local
        # CM5 historian never shrinks the 15-minute layer below the multi-year floor.
        effective_quarter_retention_days = max(
            quarter_retention_days,
            self.QUARTER_RETENTION_DAYS,
        )

        values = (
            ("raw_retention_days", raw_retention_days),
            ("minute_retention_days", minute_retention_days),
            ("quarter_retention_days", effective_quarter_retention_days),
            ("hourly_retention_days", self.HOURLY_RETENTION_DAYS),
            ("daily_retention_days", self.DAILY_RETENTION_DAYS),
        )
        for name, value in values:
            if value < 1:
                raise ValueError(f"{name} must be at least 1")

        effective_now = now or datetime.now(timezone.utc)
        if effective_now.tzinfo is None or effective_now.utcoffset() is None:
            raise ValueError("retention time must be timezone-aware")
        effective_now = effective_now.astimezone(timezone.utc)

        raw_cutoff = effective_now - timedelta(days=raw_retention_days)
        cutoffs = {
            "1m": effective_now - timedelta(days=minute_retention_days),
            "15m": effective_now - timedelta(days=effective_quarter_retention_days),
            "1h": effective_now - timedelta(days=self.HOURLY_RETENTION_DAYS),
            "1d": effective_now - timedelta(days=self.DAILY_RETENTION_DAYS),
        }

        deleted_raw = 0
        deleted_rollups: dict[str, int] = {}
        with self._connect() as connection:
            state_rows = connection.execute(
                "SELECT resolution, processed_until FROM telemetry_rollup_state"
            ).fetchall()
            processed_until = {
                str(row["resolution"]): _parse_aware_iso(str(row["processed_until"]))
                for row in state_rows
                if str(row["resolution"]) in self.ROLLUPS
            }

            if all(resolution in processed_until for resolution in self.ROLLUPS):
                safe_until = min(processed_until[resolution] for resolution in self.ROLLUPS)
                delete_before = min(raw_cutoff, safe_until)
                cursor = connection.execute(
                    """
                    DELETE FROM telemetry_samples
                    WHERE synced_at IS NOT NULL AND captured_at < ?
                    """,
                    (delete_before.isoformat(),),
                )
                deleted_raw = int(cursor.rowcount)

            for resolution, (table, _bucket_seconds) in self.ROLLUPS.items():
                cursor = connection.execute(
                    f"DELETE FROM {table} WHERE bucket_start < ?",
                    (cutoffs[resolution].isoformat(),),
                )
                deleted_rollups[resolution] = int(cursor.rowcount)

        return {"raw": deleted_raw, **deleted_rollups}
