from __future__ import annotations

from threading import RLock

from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.policy import FanSetpointPolicy

from .ports import VentilationActuator


class VentilationService:
    """Application boundary for fan commands and authoritative state."""

    def __init__(
        self,
        actuator: VentilationActuator,
        policy: FanSetpointPolicy,
    ) -> None:
        self._actuator = actuator
        self._policy = policy
        self._lock = RLock()
        self._setpoints = FanSetpoints.stopped()
        self._mode = VentilationMode.STOP

    def set_manual(self, supply_voltage: float, extract_voltage: float) -> CoreState:
        requested = FanSetpoints(supply_voltage, extract_voltage)
        validated = self._policy.validate(requested)
        with self._lock:
            self._actuator.apply(validated)
            self._setpoints = validated
            self._mode = (
                VentilationMode.STOP
                if validated == FanSetpoints.stopped()
                else VentilationMode.MANUAL
            )
            return self.state()

    def stop(self) -> CoreState:
        with self._lock:
            self._actuator.stop_all()
            self._setpoints = FanSetpoints.stopped()
            self._mode = VentilationMode.STOP
            return self.state()

    def state(self) -> CoreState:
        with self._lock:
            return CoreState(
                mode=self._mode,
                setpoints=self._setpoints,
                hardware_ready=self._actuator.ready,
            )

    def health_check(self) -> None:
        self._actuator.health_check()

    def close(self) -> None:
        with self._lock:
            try:
                self._actuator.stop_all()
            finally:
                self._actuator.close()
