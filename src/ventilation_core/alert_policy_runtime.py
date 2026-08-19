from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping

from ventilation_core.alert_policy import AlertPolicy, AlertPolicyEntry, AlertPolicyError, load_alert_policy


LOGGER = logging.getLogger(__name__)


class RuntimeAlertPolicyManager:
    """Read-only runtime holder for a validated AlertV2 policy.

    Stage 2 deliberately does not execute ``reaction`` and does not change any
    control path.  A candidate policy is accepted only after full validation.
    Failed reloads preserve the previously loaded policy (last-known-good).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = RLock()
        self._policy: AlertPolicy | None = None
        self._last_error: str | None = None
        self._last_attempt_at: str | None = None
        self._loaded_at: str | None = None
        self.reload()

    @property
    def source_path(self) -> Path:
        return self._path

    @property
    def policy(self) -> AlertPolicy | None:
        with self._lock:
            return self._policy

    @property
    def loaded(self) -> bool:
        with self._lock:
            return self._policy is not None

    def reload(self) -> bool:
        """Validate and atomically replace the active read-only policy.

        Returns ``True`` when a new candidate was accepted.  On any validation
        or I/O failure the current policy remains unchanged.
        """

        attempted_at = datetime.now(timezone.utc).isoformat()
        try:
            candidate = load_alert_policy(self._path)
        except AlertPolicyError as exc:
            with self._lock:
                self._last_attempt_at = attempted_at
                self._last_error = str(exc)
            LOGGER.warning(
                "AlertV2 policy candidate rejected; keeping last-known-good policy: %s",
                exc,
            )
            return False

        with self._lock:
            self._policy = candidate
            self._last_attempt_at = attempted_at
            self._loaded_at = attempted_at
            self._last_error = None
        LOGGER.info(
            "AlertV2 policy loaded read-only version=%s sha256=%s alerts=%s path=%s",
            candidate.policy_version,
            candidate.sha256,
            candidate.alert_count,
            candidate.source_path,
        )
        return True

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            policy = self._policy
            return {
                "runtime_mode": "read_only_mapping",
                "loaded": policy is not None,
                "policy_version": None if policy is None else policy.policy_version,
                "sha256": None if policy is None else policy.sha256,
                "alert_count": 0 if policy is None else policy.alert_count,
                "source_path": str(self._path),
                "loaded_at": self._loaded_at,
                "last_attempt_at": self._last_attempt_at,
                "last_error": self._last_error,
                "control_policy_applied": False,
            }

    def entry_for(self, code: str) -> AlertPolicyEntry | None:
        with self._lock:
            policy = self._policy
            if policy is None:
                return None
            return policy.get(code)

    def decorate_alert_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Add AlertV2 presentation metadata without changing legacy fields."""

        result = dict(payload)
        raw_code = payload.get("code")
        code = raw_code if isinstance(raw_code, str) else ""
        with self._lock:
            policy = self._policy
            if policy is None:
                result["alert_v2"] = {
                    "mapped": False,
                    "policy_version": None,
                    "reason": "policy_unavailable",
                }
                return result
            entry = policy.get(code)
            if entry is None:
                result["alert_v2"] = {
                    "mapped": False,
                    "policy_version": policy.policy_version,
                    "reason": "policy_entry_missing",
                }
                return result
            result["alert_v2"] = {
                "mapped": True,
                "policy_version": policy.policy_version,
                "enabled": entry.enabled,
                "weight": entry.weight,
                "severity": entry.severity,
                "reaction": entry.reaction,
                "scope": entry.scope,
                "affects_control": entry.affects_control,
                "hmi_color": entry.hmi_color,
                "category": entry.category,
                "correlation_group": entry.correlation_group,
                "correlation_priority": entry.correlation_priority,
                "title": entry.title,
            }
            return result

    def active_summary(self, active_alerts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Calculate the read-only HMI projection from active core alerts.

        ACK state is intentionally ignored.  Only ``active`` alerts passed by
        the caller are considered.  Disabled policy entries remain visible in
        the alert list but do not contribute to the V2 HMI weight.
        """

        alerts = tuple(active_alerts)
        with self._lock:
            policy = self._policy
            metadata = self.metadata()
            if policy is None:
                return {
                    **metadata,
                    "active_weight": None,
                    "hmi_color": None,
                    "mapped_active_alerts": 0,
                    "disabled_active_alerts": 0,
                    "unmapped_active_alerts": len(alerts),
                }

            active_weight = 0
            mapped = 0
            disabled = 0
            unmapped = 0
            for payload in alerts:
                raw_code = payload.get("code")
                code = raw_code if isinstance(raw_code, str) else ""
                entry = policy.get(code)
                if entry is None:
                    unmapped += 1
                    continue
                mapped += 1
                if not entry.enabled:
                    disabled += 1
                    continue
                active_weight = max(active_weight, entry.weight)

            color_by_weight = {
                0: "green",
                1: "blue",
                2: "yellow",
                3: "orange",
                4: "red",
            }
            return {
                **metadata,
                "active_weight": active_weight,
                "hmi_color": color_by_weight[active_weight],
                "mapped_active_alerts": mapped,
                "disabled_active_alerts": disabled,
                "unmapped_active_alerts": unmapped,
            }
