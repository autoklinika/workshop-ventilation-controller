from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from ventilation_core.application.shadow_controller import ShadowAutomationEvaluator
from ventilation_core.application.zigbee_service import ZigbeeAlertingVentilationService
from ventilation_core.domain.models import CoreState


class ShadowAlertingVentilationService(ZigbeeAlertingVentilationService):
    """Alerting + Zigbee core decorated with deterministic, strictly non-actuating SHADOW state."""

    def __init__(
        self,
        *args: object,
        shadow_evaluator: ShadowAutomationEvaluator,
        **kwargs: object,
    ) -> None:
        self._shadow_evaluator = shadow_evaluator
        super().__init__(*args, **kwargs)

    def _with_system_alerts(self, state: CoreState) -> CoreState:
        # AlertingVentilationService invokes this hook before the Zigbee decorator
        # attaches its telemetry.  Do not evaluate SHADOW here: doing so would
        # make shadow_automation observe a different (or missing) Zigbee snapshot
        # from the one eventually serialized in CoreState.
        return super()._with_system_alerts(state)

    def _with_zigbee(self, state: CoreState) -> CoreState:
        # Build one authoritative state first, then evaluate SHADOW from exactly
        # that same Zigbee snapshot.  The returned CoreState and shadow telemetry
        # therefore cannot disagree merely because an MQTT update arrived between
        # two independent Zigbee reads.
        authoritative = super()._with_zigbee(state)
        shadow = self._shadow_evaluator.evaluate(authoritative)
        return replace(authoritative, shadow_automation=shadow)

    def control_engine_configuration(self) -> dict[str, Any]:
        method = getattr(self._shadow_evaluator, "configuration", None)
        if method is None:
            raise RuntimeError("Persistent Control Engine configuration is not configured")
        return method()

    def replace_control_engine_configuration(
        self,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        method = getattr(self._shadow_evaluator, "replace_configuration", None)
        if method is None:
            raise RuntimeError("Persistent Control Engine configuration is not configured")
        return method(payload)

    def control_engine_operator_state(self) -> dict[str, Any]:
        method = getattr(self._shadow_evaluator, "operator_state", None)
        if method is None:
            raise RuntimeError("Control Engine operator runtime is not configured")
        return method()

    def replace_control_engine_operator_intent(
        self,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        method = getattr(self._shadow_evaluator, "replace_operator_intent", None)
        if method is None:
            raise RuntimeError("Control Engine operator runtime is not configured")
        return method(payload)

    def close(self) -> None:
        try:
            super().close()
        finally:
            close = getattr(self._shadow_evaluator, "close", None)
            if close is not None:
                close()
