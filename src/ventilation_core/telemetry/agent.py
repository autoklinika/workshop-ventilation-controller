from __future__ import annotations

import logging
from threading import Event, Thread
from time import monotonic
from typing import Any, Protocol

from .http_client import AIBridgeRequestTooLarge
from .store import TelemetryBatchRecord, TelemetryStore


LOGGER = logging.getLogger(__name__)


class StateReader(Protocol):
    def read_state(self) -> dict[str, Any]: ...


class BatchSender(Protocol):
    def send_batch(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class TelemetryAgent:
    RETRY_DELAYS_SECONDS = (5.0, 15.0, 30.0, 60.0)

    def __init__(
        self,
        *,
        store: TelemetryStore,
        state_reader: StateReader,
        batch_sender: BatchSender | None,
        source_id: str,
        capture_interval_seconds: float = 5.0,
        idle_sync_interval_seconds: float = 5.0,
        batch_size: int = 100,
        retention_days: int = 7,
        minute_retention_days: int = 90,
        quarter_retention_days: int = 730,
        maintenance_interval_seconds: float = 60.0,
        max_rollup_buckets_per_run: int = 240,
    ) -> None:
        if capture_interval_seconds <= 0:
            raise ValueError("Capture interval must be positive")
        if idle_sync_interval_seconds <= 0:
            raise ValueError("Sync interval must be positive")
        if not 1 <= batch_size <= 500:
            raise ValueError("Batch size must be in range 1..500")
        if retention_days < 1:
            raise ValueError("Raw retention must be at least 1 day")
        if minute_retention_days < 1:
            raise ValueError("Minute retention must be at least 1 day")
        if quarter_retention_days < 1:
            raise ValueError("Quarter-hour retention must be at least 1 day")
        if maintenance_interval_seconds <= 0:
            raise ValueError("Maintenance interval must be positive")
        if max_rollup_buckets_per_run < 1:
            raise ValueError("max_rollup_buckets_per_run must be at least 1")
        if not source_id:
            raise ValueError("source_id must not be empty")

        self.store = store
        self.state_reader = state_reader
        self.batch_sender = batch_sender
        self.source_id = source_id
        self.capture_interval_seconds = capture_interval_seconds
        self.idle_sync_interval_seconds = idle_sync_interval_seconds
        self.batch_size = batch_size
        self.retention_days = retention_days
        self.minute_retention_days = minute_retention_days
        self.quarter_retention_days = quarter_retention_days
        self.maintenance_interval_seconds = maintenance_interval_seconds
        self.max_rollup_buckets_per_run = max_rollup_buckets_per_run

    @property
    def sync_enabled(self) -> bool:
        return self.batch_sender is not None

    def capture_once(self) -> None:
        state = self.state_reader.read_state()
        sample = self.store.append_snapshot(state)
        LOGGER.debug(
            "Captured telemetry sample sequence=%d sample_id=%s",
            sample.sequence,
            sample.sample_id,
        )

    def sync_once(self) -> bool:
        sender = self.batch_sender
        if sender is None:
            return False

        batch = self.store.reserve_batch(self.batch_size)
        if batch is None:
            return False

        payload = self._build_payload(batch)
        try:
            ack = sender.send_batch(payload)
            self._validate_ack(batch, ack)
        except AIBridgeRequestTooLarge as exc:
            self.store.record_attempt(batch.batch_id, str(exc))
            if len(batch.samples) <= 1:
                LOGGER.error(
                    "Single telemetry sample exceeds AI Bridge request limit; "
                    "sample remains pending batch_id=%s",
                    batch.batch_id,
                )
                raise

            released = self.store.release_batch(batch.batch_id)
            if released != len(batch.samples):
                raise RuntimeError(
                    f"Failed to release oversized batch {batch.batch_id}: "
                    f"expected {len(batch.samples)} rows, released {released}"
                ) from exc

            previous_size = self.batch_size
            self.batch_size = max(1, min(self.batch_size, len(batch.samples) // 2))
            LOGGER.warning(
                "AI Bridge rejected oversized telemetry batch; released=%d "
                "batch_size=%d->%d pending samples preserved",
                released,
                previous_size,
                self.batch_size,
            )
            return False
        except Exception as exc:
            self.store.record_attempt(batch.batch_id, str(exc))
            raise

        self.store.record_attempt(batch.batch_id, None)
        marked = self.store.mark_batch_synced(batch.batch_id)
        if marked != len(batch.samples):
            raise RuntimeError(
                f"Local sync state mismatch for batch {batch.batch_id}: "
                f"expected {len(batch.samples)} rows, marked {marked}"
            )
        LOGGER.info(
            "Telemetry batch synced batch_id=%s samples=%d stored=%s duplicates=%s",
            batch.batch_id,
            len(batch.samples),
            ack.get("stored"),
            ack.get("duplicates"),
        )
        return True

    def maintenance_once(self) -> None:
        built = self.store.build_rollups(
            max_buckets_per_resolution=self.max_rollup_buckets_per_run,
        )
        deleted = self.store.prune_history(
            raw_retention_days=self.retention_days,
            minute_retention_days=self.minute_retention_days,
            quarter_retention_days=self.quarter_retention_days,
        )
        if any(built.values()) or any(deleted.values()):
            LOGGER.info(
                "Telemetry history maintenance rollups_1m=%d rollups_15m=%d "
                "deleted_raw=%d deleted_1m=%d deleted_15m=%d",
                built["1m"],
                built["15m"],
                deleted["raw"],
                deleted["1m"],
                deleted["15m"],
            )

    def run(self, stop_event: Event) -> None:
        capture_thread = Thread(
            target=self._capture_loop,
            args=(stop_event,),
            name="telemetry-capture",
            daemon=True,
        )
        threads = [capture_thread]

        if self.sync_enabled:
            threads.append(
                Thread(
                    target=self._sync_loop,
                    args=(stop_event,),
                    name="telemetry-sync",
                    daemon=True,
                )
            )
        else:
            LOGGER.warning(
                "Telemetry remote synchronization is disabled; local capture remains active"
            )

        for thread in threads:
            thread.start()

        while not stop_event.wait(0.5):
            pass

        capture_thread.join(timeout=max(2.0, self.capture_interval_seconds + 1.0))
        for thread in threads[1:]:
            thread.join(timeout=10.0)

    def _capture_loop(self, stop_event: Event) -> None:
        next_maintenance = monotonic()
        while not stop_event.is_set():
            try:
                self.capture_once()
            except Exception:
                LOGGER.exception("Telemetry snapshot capture failed; ventilation-core is unaffected")

            current = monotonic()
            if current >= next_maintenance:
                try:
                    self.maintenance_once()
                except Exception:
                    LOGGER.exception("Telemetry history maintenance failed; capture remains active")
                next_maintenance = current + self.maintenance_interval_seconds

            stop_event.wait(self.capture_interval_seconds)

    def _sync_loop(self, stop_event: Event) -> None:
        failure_index = 0
        while not stop_event.is_set():
            try:
                sent = self.sync_once()
                failure_index = 0
                if sent:
                    if stop_event.wait(0.05):
                        return
                    continue
                stop_event.wait(self.idle_sync_interval_seconds)
            except Exception:
                LOGGER.exception("Telemetry sync failed; pending samples remain local")
                delay = self.RETRY_DELAYS_SECONDS[min(failure_index, len(self.RETRY_DELAYS_SECONDS) - 1)]
                failure_index += 1
                stop_event.wait(delay)

    def _build_payload(self, batch: TelemetryBatchRecord) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source_id": self.source_id,
            "batch_id": batch.batch_id,
            "created_at": batch.created_at,
            "samples": [
                {
                    "sample_id": sample.sample_id,
                    "sequence": sample.sequence,
                    "captured_at": sample.captured_at,
                    "metrics": sample.metrics,
                }
                for sample in batch.samples
            ],
        }

    def _validate_ack(self, batch: TelemetryBatchRecord, ack: dict[str, Any]) -> None:
        expected = len(batch.samples)
        if ack.get("schema_version") != 1:
            raise RuntimeError("AI Bridge ACK has unsupported schema_version")
        if ack.get("source_id") != self.source_id:
            raise RuntimeError("AI Bridge ACK source_id mismatch")
        if ack.get("batch_id") != batch.batch_id:
            raise RuntimeError("AI Bridge ACK batch_id mismatch")
        if ack.get("status") != "accepted":
            raise RuntimeError("AI Bridge did not accept telemetry batch")

        received = ack.get("received")
        stored = ack.get("stored")
        duplicates = ack.get("duplicates")
        rejected = ack.get("rejected")
        if not all(isinstance(value, int) for value in (received, stored, duplicates, rejected)):
            raise RuntimeError("AI Bridge ACK counters are invalid")
        if received != expected:
            raise RuntimeError(f"AI Bridge ACK received={received}, expected={expected}")
        if rejected != 0:
            raise RuntimeError(f"AI Bridge rejected {rejected} telemetry samples")
        if stored + duplicates != expected:
            raise RuntimeError(
                "AI Bridge ACK stored + duplicates does not match transmitted sample count"
            )
