from __future__ import annotations

from typing import Any, Callable

from ventilation_core.alert_policy_runtime import RuntimeAlertPolicyManager


class _AlertV2StateView:
    def __init__(
        self,
        state: Any,
        manager: RuntimeAlertPolicyManager,
        service_plane_diagnostics: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._state = state
        self._manager = manager
        self._service_plane_diagnostics = service_plane_diagnostics

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)

    def to_dict(self) -> dict[str, Any]:
        payload = self._state.to_dict()
        raw_active = payload.get("active_alarms")
        active = raw_active if isinstance(raw_active, list) else []
        decorated = [
            self._manager.decorate_alert_payload(item)
            if isinstance(item, dict)
            else item
            for item in active
        ]
        payload["active_alarms"] = decorated
        policy_inputs = [item for item in active if isinstance(item, dict)]
        summary = self._manager.active_summary(policy_inputs)
        if self._service_plane_diagnostics is not None:
            try:
                summary["service_plane"] = self._service_plane_diagnostics()
            except Exception as exc:
                summary["service_plane"] = {
                    "monitor": None,
                    "correlation": None,
                    "control_policy_applied": False,
                    "diagnostics_error": str(exc),
                }
        payload["alert_v2"] = summary
        return payload


class _AlertV2RecordView:
    def __init__(self, record: Any, manager: RuntimeAlertPolicyManager) -> None:
        self._record = record
        self._manager = manager

    def __getattr__(self, name: str) -> Any:
        return getattr(self._record, name)

    def to_dict(self) -> dict[str, Any]:
        return self._manager.decorate_alert_payload(self._record.to_dict())


class AlertV2ReadOnlyPolicyService:
    """Decorate the existing service contract with AlertV2 read-only metadata.

    This wrapper deliberately delegates every control method unchanged.  It
    only enriches serialized state/alert records.  No AlertV2 ``reaction`` is
    executed in this stage.
    """

    def __init__(
        self,
        delegate: Any,
        manager: RuntimeAlertPolicyManager,
        *,
        service_plane_diagnostics: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._delegate = delegate
        self._manager = manager
        self._service_plane_diagnostics = service_plane_diagnostics

    @property
    def alert_policy_manager(self) -> RuntimeAlertPolicyManager:
        return self._manager

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def state(self) -> _AlertV2StateView:
        return _AlertV2StateView(
            self._delegate.state(),
            self._manager,
            self._service_plane_diagnostics,
        )

    def active_alerts(self) -> tuple[_AlertV2RecordView, ...]:
        return tuple(
            _AlertV2RecordView(record, self._manager)
            for record in self._delegate.active_alerts()
        )

    def alert_history(self, limit: int = 200) -> tuple[_AlertV2RecordView, ...]:
        return tuple(
            _AlertV2RecordView(record, self._manager)
            for record in self._delegate.alert_history(limit)
        )

    def acknowledge_alert(self, alert_id: int) -> _AlertV2RecordView:
        return _AlertV2RecordView(
            self._delegate.acknowledge_alert(alert_id),
            self._manager,
        )
