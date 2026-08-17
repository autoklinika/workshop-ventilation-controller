from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol

from ventilation_core.domain.alerts import AlertRecord, AlertSignal
from ventilation_core.domain.models import AlarmState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AlertStore(Protocol):
    def list_active(self) -> tuple[AlertRecord, ...]: ...
    def list_history(self, limit: int) -> tuple[AlertRecord, ...]: ...
    def create(self, signal: AlertSignal, active_since: str) -> AlertRecord: ...
    def update_active(self, record: AlertRecord, signal: AlertSignal) -> AlertRecord: ...
    def acknowledge(self, alert_id: int, acknowledged_at: str) -> AlertRecord: ...
    def clear(
        self,
        alert_id: int,
        cleared_at: str,
        final_occurrences: int | None = None,
    ) -> AlertRecord: ...
    def close(self) -> None: ...


class MemoryAlertStore:
    """In-memory store used by dependency-isolated core tests."""

    def __init__(self) -> None:
        self._records: list[AlertRecord] = []
        self._next_id = 1
        self._lock = RLock()

    def list_active(self) -> tuple[AlertRecord, ...]:
        with self._lock:
            return tuple(record for record in self._records if record.active)

    def list_history(self, limit: int) -> tuple[AlertRecord, ...]:
        with self._lock:
            return tuple(reversed(self._records[-limit:]))

    def create(self, signal: AlertSignal, active_since: str) -> AlertRecord:
        with self._lock:
            record = AlertRecord(
                alert_id=self._next_id,
                key=signal.key,
                code=signal.code,
                source=signal.source,
                severity=signal.severity,
                message=signal.message,
                detail=signal.detail,
                active_since=active_since,
                acknowledged_at=None,
                cleared_at=None,
                occurrences=signal.occurrences,
            )
            self._next_id += 1
            self._records.append(record)
            return record

    def update_active(self, record: AlertRecord, signal: AlertSignal) -> AlertRecord:
        with self._lock:
            updated = replace(
                record,
                code=signal.code,
                source=signal.source,
                severity=signal.severity,
                message=signal.message,
                detail=signal.detail,
                occurrences=max(record.occurrences, signal.occurrences),
            )
            self._replace(updated)
            return updated

    def acknowledge(self, alert_id: int, acknowledged_at: str) -> AlertRecord:
        with self._lock:
            record = self._find(alert_id)
            if not record.active:
                raise ValueError(f"Alert {alert_id} is not active")
            updated = replace(record, acknowledged_at=record.acknowledged_at or acknowledged_at)
            self._replace(updated)
            return updated

    def clear(
        self,
        alert_id: int,
        cleared_at: str,
        final_occurrences: int | None = None,
    ) -> AlertRecord:
        with self._lock:
            record = self._find(alert_id)
            if not record.active:
                return record
            updated = replace(
                record,
                cleared_at=cleared_at,
                occurrences=max(record.occurrences, final_occurrences or record.occurrences),
            )
            self._replace(updated)
            return updated

    def close(self) -> None:
        return

    def _find(self, alert_id: int) -> AlertRecord:
        for record in self._records:
            if record.alert_id == alert_id:
                return record
        raise ValueError(f"Unknown alert id: {alert_id}")

    def _replace(self, updated: AlertRecord) -> None:
        for index, record in enumerate(self._records):
            if record.alert_id == updated.alert_id:
                self._records[index] = updated
                return
        raise ValueError(f"Unknown alert id: {updated.alert_id}")


class AlertRegistry:
    """Authoritative alert lifecycle owned by ventilation-core.

    Occurrence-only growth is kept current in memory for clients, but persisted
    in batches to avoid continuous eMMC writes during a long-running fault. The
    exact final count is persisted atomically when the incident is cleared.
    """

    def __init__(
        self,
        store: AlertStore | None = None,
        *,
        occurrence_persist_step: int = 30,
    ) -> None:
        if (
            isinstance(occurrence_persist_step, bool)
            or not isinstance(occurrence_persist_step, int)
            or occurrence_persist_step < 1
        ):
            raise ValueError("occurrence_persist_step must be a positive integer")
        self._store: AlertStore = store or MemoryAlertStore()
        self._occurrence_persist_step = occurrence_persist_step
        self._lock = RLock()
        self._latest_occurrences = {
            record.key: record.occurrences for record in self._store.list_active()
        }

    def reconcile(
        self,
        signals: tuple[AlertSignal, ...] | list[AlertSignal],
    ) -> tuple[AlertRecord, ...]:
        with self._lock:
            by_key = {signal.key: signal for signal in signals}
            active = {record.key: record for record in self._store.list_active()}
            now = _now_iso()

            for key, signal in by_key.items():
                latest = max(self._latest_occurrences.get(key, 0), signal.occurrences)
                self._latest_occurrences[key] = latest
                record = active.get(key)
                if record is None:
                    active[key] = self._store.create(
                        replace(signal, occurrences=latest),
                        now,
                    )
                elif self._metadata_changed(record, signal) or (
                    latest >= record.occurrences + self._occurrence_persist_step
                ):
                    active[key] = self._store.update_active(
                        record,
                        replace(signal, occurrences=latest),
                    )

            for key, record in tuple(active.items()):
                if key not in by_key:
                    final_occurrences = max(
                        record.occurrences,
                        self._latest_occurrences.pop(key, record.occurrences),
                    )
                    self._store.clear(
                        record.alert_id,
                        now,
                        final_occurrences=final_occurrences,
                    )

            return self._active_records_unlocked()

    def activate(self, signal: AlertSignal) -> AlertRecord:
        """Activate/update one condition without clearing unrelated alerts."""
        with self._lock:
            latest = max(
                self._latest_occurrences.get(signal.key, 0),
                signal.occurrences,
            )
            self._latest_occurrences[signal.key] = latest
            for record in self._store.list_active():
                if record.key != signal.key:
                    continue
                if self._metadata_changed(record, signal) or (
                    latest >= record.occurrences + self._occurrence_persist_step
                ):
                    record = self._store.update_active(
                        record,
                        replace(signal, occurrences=latest),
                    )
                return self._with_latest_occurrences(record)
            return self._store.create(replace(signal, occurrences=latest), _now_iso())

    def clear_key(self, key: str) -> AlertRecord | None:
        with self._lock:
            for record in self._store.list_active():
                if record.key == key:
                    final_occurrences = max(
                        record.occurrences,
                        self._latest_occurrences.pop(key, record.occurrences),
                    )
                    return self._store.clear(
                        record.alert_id,
                        _now_iso(),
                        final_occurrences=final_occurrences,
                    )
            self._latest_occurrences.pop(key, None)
            return None

    def acknowledge(self, alert_id: int) -> AlertRecord:
        if isinstance(alert_id, bool) or not isinstance(alert_id, int) or alert_id < 1:
            raise ValueError("alert_id must be a positive integer")
        with self._lock:
            record = self._store.acknowledge(alert_id, _now_iso())
            return self._with_latest_occurrences(record)

    def active_records(self) -> tuple[AlertRecord, ...]:
        with self._lock:
            return self._active_records_unlocked()

    def active_alarm_states(self) -> tuple[AlarmState, ...]:
        return tuple(record.to_alarm_state() for record in self.active_records())

    def history(self, limit: int = 200) -> tuple[AlertRecord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Alert history limit must be an integer in range 1..1000")
        with self._lock:
            return tuple(
                self._with_latest_occurrences(record)
                for record in self._store.list_history(limit)
            )

    def close(self) -> None:
        with self._lock:
            self._store.close()

    def _active_records_unlocked(self) -> tuple[AlertRecord, ...]:
        return tuple(
            self._with_latest_occurrences(record)
            for record in self._store.list_active()
        )

    def _with_latest_occurrences(self, record: AlertRecord) -> AlertRecord:
        if not record.active:
            return record
        latest = self._latest_occurrences.get(record.key, record.occurrences)
        if latest <= record.occurrences:
            return record
        return replace(record, occurrences=latest)

    @staticmethod
    def _metadata_changed(record: AlertRecord, signal: AlertSignal) -> bool:
        return (
            record.code != signal.code
            or record.source != signal.source
            or record.severity != signal.severity
            or record.message != signal.message
            or record.detail != signal.detail
        )
