from __future__ import annotations

import logging
from dataclasses import replace
from typing import Protocol

from ventilation_core.application.alerting_service import AlertingVentilationService
from ventilation_core.domain.models import CoreState
from ventilation_core.domain.zigbee import ZigbeeMqttState


LOGGER = logging.getLogger(__name__)


class ZigbeeMonitor(Protocol):
    def state(self) -> ZigbeeMqttState: ...

    def health_check(self) -> None: ...

    def close(self) -> None: ...


class ZigbeeAlertingVentilationService(AlertingVentilationService):
    """Alerting service extended with read-only Zigbee telemetry state."""

    def __init__(
        self,
        *args: object,
        zigbee: ZigbeeMonitor | None = None,
        **kwargs: object,
    ) -> None:
        self._zigbee = zigbee
        super().__init__(*args, **kwargs)

    def state(self) -> CoreState:
        return self._with_zigbee(super().state())

    def health_check(self) -> CoreState:
        if self._zigbee is not None:
            try:
                self._zigbee.health_check()
            except Exception:
                # Zigbee is telemetry-only at this stage. A monitor failure
                # must never interrupt existing ventilation supervision.
                LOGGER.exception("Zigbee monitor health check failed")
        return self._with_zigbee(super().health_check())

    def set_manual(self, supply_voltage: float, extract_voltage: float) -> CoreState:
        return self._with_zigbee(super().set_manual(supply_voltage, extract_voltage))

    def stop(self) -> CoreState:
        return self._with_zigbee(super().stop())

    def close(self) -> None:
        # Preserve the existing shutdown safety ordering: first force the
        # ventilation outputs to zero and close core hardware, then stop the
        # telemetry-only MQTT client.
        try:
            super().close()
        finally:
            if self._zigbee is not None:
                try:
                    self._zigbee.close()
                except Exception:
                    LOGGER.exception("Failed to close Zigbee MQTT monitor")

    def _with_zigbee(self, state: CoreState) -> CoreState:
        if self._zigbee is None:
            return state
        try:
            return replace(state, zigbee=self._zigbee.state())
        except Exception:
            # Never turn a successful fan command into an apparent failure just
            # because the read-only Zigbee state cannot be collected.
            LOGGER.exception("Unable to read Zigbee state")
            return state
