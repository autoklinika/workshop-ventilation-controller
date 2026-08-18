from __future__ import annotations

from dataclasses import replace

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
        authoritative = super()._with_system_alerts(state)
        shadow = self._shadow_evaluator.evaluate(authoritative)
        return replace(authoritative, shadow_automation=shadow)
