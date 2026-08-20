from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class AlertHistoryUnavailable(RuntimeError):
    """Raised when the local alert journal cannot be read safely."""


class SqliteAlertHistoryReader:
    """Read-only paged view of the core-owned alert journal.

    The reader never mutates ``alerts.sqlite3``. It exposes lightweight date
    summaries and lazy day pages for WebUI so a multi-year journal does not have
    to be transferred to the browser on every refresh.
    """

    DEFAULT_INDEX_WINDOW_DAYS = 90
    MAX_INDEX_WINDOW_DAYS = 366
    DEFAULT_DAY_PAGE_SIZE = 100
    MAX_DAY_PAGE_SIZE = 200

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def day_index(
        self,
        *,
        timezone_name: str,
        before_day: str | None = None,
        window_days: int = DEFAULT_INDEX_WINDOW_DAYS,
    ) -> dict[str, Any]:
        zone = self._zone(timezone_name)
        if isinstance(window_days, bool) or not isinstance(window_days, int):
            raise ValueError("window_days must be an integer")
        if not 1 <= window_days <= self.MAX_INDEX_WINDOW_DAYS:
            raise ValueError(
                f"window_days must be within 1..{self.MAX_INDEX_WINDOW_DAYS}"
            )

        if before_day is None:
            end_day = datetime.now(zone).date() + timedelta(days=1)
        else:
            end_day = self._day(before_day)
        start_day = end_day - timedelta(days=window_days)

        start_at = self._local_midnight_utc(start_day, zone)
        end_at = self._local_midnight_utc(end_day, zone)

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT cleared_at, severity
                FROM alerts
                WHERE cleared_at IS NOT NULL
                  AND cleared_at >= ?
                  AND cleared_at < ?
                ORDER BY cleared_at DESC
                """,
                (start_at, end_at),
            ).fetchall()

            summaries: dict[str, dict[str, Any]] = {}
            for row in rows:
                cleared = self._timestamp(row["cleared_at"])
                if cleared is None:
                    continue
                key = cleared.astimezone(zone).date().isoformat()
                summary = summaries.setdefault(
                    key,
                    {
                        "day": key,
                        "count": 0,
                        "critical": 0,
                        "warning": 0,
                        "other": 0,
                    },
                )
                summary["count"] += 1
                severity = str(row["severity"] or "").lower()
                if severity == "critical":
                    summary["critical"] += 1
                elif severity == "warning":
                    summary["warning"] += 1
                else:
                    summary["other"] += 1

            aggregate = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_closed,
                    MIN(cleared_at) AS oldest_cleared_at,
                    MAX(cleared_at) AS newest_cleared_at
                FROM alerts
                WHERE cleared_at IS NOT NULL
                """
            ).fetchone()

            has_older = (
                connection.execute(
                    """
                    SELECT 1
                    FROM alerts
                    WHERE cleared_at IS NOT NULL
                      AND cleared_at < ?
                    LIMIT 1
                    """,
                    (start_at,),
                ).fetchone()
                is not None
            )

            days = [summaries[key] for key in sorted(summaries, reverse=True)]
            return {
                "timezone": timezone_name,
                "window": {
                    "start_day": start_day.isoformat(),
                    "end_day_exclusive": end_day.isoformat(),
                    "window_days": window_days,
                },
                "days": days,
                "has_older": has_older,
                "next_before_day": start_day.isoformat() if has_older else None,
                "total_closed": int(aggregate["total_closed"] or 0),
                "oldest_cleared_at": aggregate["oldest_cleared_at"],
                "newest_cleared_at": aggregate["newest_cleared_at"],
            }
        finally:
            connection.close()

    def query_day(
        self,
        *,
        day: str,
        timezone_name: str,
        limit: int = DEFAULT_DAY_PAGE_SIZE,
        before_cleared_at: str | None = None,
        before_alert_id: int | None = None,
    ) -> dict[str, Any]:
        local_day = self._day(day)
        zone = self._zone(timezone_name)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        if not 1 <= limit <= self.MAX_DAY_PAGE_SIZE:
            raise ValueError(f"limit must be within 1..{self.MAX_DAY_PAGE_SIZE}")

        if (before_cleared_at is None) != (before_alert_id is None):
            raise ValueError(
                "before_cleared_at and before_alert_id must be supplied together"
            )
        if before_alert_id is not None and (
            isinstance(before_alert_id, bool)
            or not isinstance(before_alert_id, int)
            or before_alert_id < 1
        ):
            raise ValueError("before_alert_id must be a positive integer")
        if before_cleared_at is not None and self._timestamp(before_cleared_at) is None:
            raise ValueError("before_cleared_at must be an ISO-8601 timestamp")

        start_at = self._local_midnight_utc(local_day, zone)
        end_at = self._local_midnight_utc(local_day + timedelta(days=1), zone)

        where_cursor = ""
        parameters: list[Any] = [start_at, end_at]
        if before_cleared_at is not None and before_alert_id is not None:
            where_cursor = (
                " AND (cleared_at < ? OR (cleared_at = ? AND alert_id < ?))"
            )
            parameters.extend(
                [before_cleared_at, before_cleared_at, before_alert_id]
            )
        parameters.append(limit + 1)

        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT *
                FROM alerts
                WHERE cleared_at IS NOT NULL
                  AND cleared_at >= ?
                  AND cleared_at < ?
                  {where_cursor}
                ORDER BY cleared_at DESC, alert_id DESC
                LIMIT ?
                """,
                tuple(parameters),
            ).fetchall()

            total_for_day = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM alerts
                    WHERE cleared_at IS NOT NULL
                      AND cleared_at >= ?
                      AND cleared_at < ?
                    """,
                    (start_at, end_at),
                ).fetchone()[0]
            )

            has_more = len(rows) > limit
            visible = rows[:limit]
            records = [self._record_to_dict(row) for row in visible]
            next_cursor = None
            if has_more and visible:
                last = visible[-1]
                next_cursor = {
                    "before_cleared_at": str(last["cleared_at"]),
                    "before_alert_id": int(last["alert_id"]),
                }

            return {
                "timezone": timezone_name,
                "day": local_day.isoformat(),
                "records": records,
                "returned": len(records),
                "total_for_day": total_for_day,
                "has_more": has_more,
                "next_cursor": next_cursor,
            }
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        if not self._path.is_file():
            raise AlertHistoryUnavailable(
                f"alert history database is not available: {self._path}"
            )
        try:
            connection = sqlite3.connect(
                f"file:{self._path}?mode=ro",
                uri=True,
                timeout=5.0,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            return connection
        except sqlite3.Error as exc:
            raise AlertHistoryUnavailable(
                f"alert history database cannot be opened: {exc}"
            ) from exc

    @staticmethod
    def _zone(name: str) -> ZoneInfo:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("timezone must be a non-empty IANA timezone name")
        try:
            return ZoneInfo(name.strip())
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {name}") from exc

    @staticmethod
    def _day(value: str) -> date:
        if not isinstance(value, str) or not value:
            raise ValueError("day must be an ISO date YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("day must be an ISO date YYYY-MM-DD") from exc

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _local_midnight_utc(local_day: date, zone: ZoneInfo) -> str:
        local = datetime.combine(local_day, time.min, tzinfo=zone)
        return local.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _record_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        acknowledged_at = (
            None if row["acknowledged_at"] is None else str(row["acknowledged_at"])
        )
        return {
            "alert_id": int(row["alert_id"]),
            "key": str(row["alert_key"]),
            "code": str(row["code"]),
            "source": str(row["source"]),
            "severity": str(row["severity"]),
            "message": str(row["message"]),
            "detail": str(row["detail"]),
            "active_since": str(row["active_since"]),
            "acknowledged": acknowledged_at is not None,
            "acknowledged_at": acknowledged_at,
            "active": False,
            "cleared_at": str(row["cleared_at"]),
            "occurrences": int(row["occurrences"]),
        }
