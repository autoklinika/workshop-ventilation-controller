from __future__ import annotations

from dataclasses import replace

from ventilation_core.application.power_scheduler import HOST_POWER_REQUEST_FAILED, RTC_WAKE_ARM_FAILED
from ventilation_core.application.power_scheduler_runtime import PowerSchedulerRuntime
from ventilation_core.application.shadow_service import ShadowAlertingVentilationService
from ventilation_core.domain.alerts import AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity, CoreState


class PowerSchedulingVentilationService(ShadowAlertingVentilationService):
    """Authoritative core service decorated with Power Scheduler diagnostics.

    The worker is the only automatic execution owner.  State serialization is
    read-only and merely publishes the latest runtime snapshot.
    """

    def __init__(
        self,
        *args: object,
        power_scheduler_runtime: PowerSchedulerRuntime | None = None,
        **kwargs: object,
    ) -> None:
        self._power_scheduler_runtime = power_scheduler_runtime
        super().__init__(*args, **kwargs)

    def _with_system_alerts(self, state: CoreState) -> CoreState:
        authoritative = super()._with_system_alerts(state)
        runtime = self._power_scheduler_runtime
        if runtime is None:
            return authoritative
        return replace(authoritative, power_scheduler=runtime.snapshot().to_dict())

    def _extra_alert_signals(self, state: CoreState) -> list[AlertSignal]:
        signals = super()._extra_alert_signals(state)
        runtime = self._power_scheduler_runtime
        if runtime is None:
            return signals
        snapshot = runtime.snapshot()
        alert = snapshot.state.alert_code
        if alert == RTC_WAKE_ARM_FAILED:
            signals.append(
                AlertSignal(
                    key="power-scheduler:rtc-wake-arm",
                    code=AlarmCode.RTC_WAKE_ARM_FAILED,
                    source="power_scheduler",
                    severity=AlarmSeverity.WARNING,
                    message="Power Scheduler: nie udało się uzbroić i zweryfikować RTC wake",
                    detail=snapshot.state.last_error,
                )
            )
        elif alert == HOST_POWER_REQUEST_FAILED:
            signals.append(
                AlertSignal(
                    key="power-scheduler:host-power",
                    code=AlarmCode.HOST_POWER_REQUEST_FAILED,
                    source="power_scheduler",
                    severity=AlarmSeverity.WARNING,
                    message="Power Scheduler: planowane wyłączenie CM5 zostało odrzucone",
                    detail=snapshot.state.last_error,
                )
            )
        return signals

    def close(self) -> None:
        runtime = self._power_scheduler_runtime
        if runtime is not None:
            runtime.close()
        super().close()
