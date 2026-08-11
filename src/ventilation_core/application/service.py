from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import RLock

from ventilation_core.domain.aero_control import AeroControlCommand, AeroControlResult
from ventilation_core.domain.models import (
    AlarmCode,
    AlarmSeverity,
    AlarmState,
    CoreState,
    FanSetpoints,
    VentilationMode,
)
from ventilation_core.domain.policy import FanSetpointPolicy

from .ports import AeroBusMonitor, SensorBusMonitor, TachoMonitor, VentilationActuator


LOGGER = logging.getLogger(__name__)


class HardwareFaultActiveError(RuntimeError):
    """Raised when a fan command is rejected because DAC state is not trustworthy."""


class AeroControlUnavailableError(RuntimeError):
    """Raised when AERO BUS cannot safely accept a control command."""


class VentilationService:
    """Application boundary for fan commands, health supervision and state."""

    DAC_ALARM_MESSAGE = "Brak komunikacji z DAC DFR0971"

    def __init__(
        self,
        actuator: VentilationActuator,
        policy: FanSetpointPolicy,
        hardware_failure_threshold: int = 3,
        sensor_bus: SensorBusMonitor | None = None,
        aero_bus: AeroBusMonitor | None = None,
        tacho: TachoMonitor | None = None,
    ) -> None:
        if hardware_failure_threshold < 1:
            raise ValueError("Hardware failure threshold must be at least 1")
        self._actuator = actuator
        self._policy = policy
        self._hardware_failure_threshold = hardware_failure_threshold
        self._sensor_bus = sensor_bus
        self._aero_bus = aero_bus
        self._tacho = tacho
        self._lock = RLock()
        self._setpoints = FanSetpoints.stopped()
        self._mode = VentilationMode.STOP
        self._output_state_known = actuator.ready
        self._consecutive_hardware_failures = 0
        self._recovery_required = not actuator.ready
        self._active_alarms: dict[AlarmCode, AlarmState] = {}

        if not actuator.ready:
            error = actuator.last_error or "DAC was not ready during ventilation-core startup"
            self._consecutive_hardware_failures = hardware_failure_threshold
            self._activate_dac_alarm(error)
            self._mode = VentilationMode.FAULT

    def set_manual(self, supply_voltage: float, extract_voltage: float) -> CoreState:
        requested = FanSetpoints(supply_voltage, extract_voltage)
        validated = self._policy.validate(requested)
        with self._lock:
            self._require_operational_hardware()
            try:
                self._actuator.apply(validated)
            except Exception as exc:
                self._record_hardware_failure(exc, immediate_alarm=True)
                raise
            self._setpoints = validated
            self._mode = (
                VentilationMode.STOP
                if validated == FanSetpoints.stopped()
                else VentilationMode.MANUAL
            )
            self._output_state_known = True
            return self.state()

    def control_aero(self, command: AeroControlCommand) -> AeroControlResult:
        with self._lock:
            if self._aero_bus is None:
                raise AeroControlUnavailableError("AERO BUS is not configured")
            state = self._aero_bus.state()
            if not state.worker_alive or not state.ready or not state.online or not state.usable:
                raise AeroControlUnavailableError("AERO BUS is not ready for control")
            if state.control_busy:
                raise AeroControlUnavailableError("AERO control command already in progress")
            return self._aero_bus.execute_control(command)

    def stop(self) -> CoreState:
        with self._lock:
            try:
                if self._recovery_required or not self._actuator.ready:
                    self._actuator.recover()
                else:
                    self._actuator.stop_all()
            except Exception as exc:
                self._record_hardware_failure(exc, immediate_alarm=True)
                raise
            self._complete_safe_recovery()
            return self.state()

    def state(self) -> CoreState:
        with self._lock:
            sensor_bus_state = None if self._sensor_bus is None else self._sensor_bus.state()
            aero_bus_state = None if self._aero_bus is None else self._aero_bus.state()
            tacho_state = None if self._tacho is None else self._tacho.state()
            return CoreState(
                mode=self._mode,
                setpoints=self._setpoints,
                hardware_ready=self._actuator.ready and not self._recovery_required,
                output_state_known=self._output_state_known,
                consecutive_hardware_failures=self._consecutive_hardware_failures,
                active_alarms=tuple(self._active_alarms.values()),
                sensor_bus=sensor_bus_state,
                aero_bus=aero_bus_state,
                tacho=tacho_state,
            )

    def health_check(self) -> CoreState:
        """Supervise DAC and independent read-only/RS-485 monitors."""
        with self._lock:
            try:
                if self._recovery_required or not self._actuator.ready:
                    self._actuator.recover()
                    self._complete_safe_recovery()
                else:
                    self._actuator.health_check()
                    self._consecutive_hardware_failures = 0
                    self._output_state_known = True
            except Exception as exc:
                self._record_hardware_failure(exc, immediate_alarm=False)

            if self._sensor_bus is not None:
                try:
                    self._sensor_bus.health_check()
                except Exception:
                    LOGGER.exception("SENSOR BUS worker health check failed")

            if self._aero_bus is not None:
                try:
                    self._aero_bus.health_check()
                except Exception:
                    LOGGER.exception("AERO BUS worker health check failed")

            if self._tacho is not None:
                try:
                    self._tacho.health_check()
                except Exception:
                    LOGGER.exception("TACHO monitor health check failed")
            return self.state()

    def close(self) -> None:
        with self._lock:
            try:
                self._actuator.stop_all()
            except Exception:
                LOGGER.exception("Failed to force DAC outputs to zero during shutdown")
            finally:
                try:
                    self._actuator.close()
                finally:
                    try:
                        if self._sensor_bus is not None:
                            self._sensor_bus.close()
                    finally:
                        try:
                            if self._aero_bus is not None:
                                self._aero_bus.close()
                        finally:
                            if self._tacho is not None:
                                self._tacho.close()

    def _require_operational_hardware(self) -> None:
        if self._recovery_required or not self._actuator.ready or self._active_alarms:
            raise HardwareFaultActiveError(
                "DAC is not ready; wait for safe recovery before issuing fan setpoints"
            )

    def _record_hardware_failure(
        self,
        exc: Exception,
        *,
        immediate_alarm: bool,
    ) -> None:
        error = str(exc)
        self._consecutive_hardware_failures += 1
        self._output_state_known = False
        self._recovery_required = True
        LOGGER.warning(
            "DAC communication failure %d/%d: %s",
            self._consecutive_hardware_failures,
            self._hardware_failure_threshold,
            error,
        )
        if immediate_alarm or (
            self._consecutive_hardware_failures >= self._hardware_failure_threshold
        ):
            self._activate_dac_alarm(error)
            self._mode = VentilationMode.FAULT

    def _activate_dac_alarm(self, error: str) -> None:
        existing = self._active_alarms.get(AlarmCode.DAC_COMMUNICATION_LOST)
        active_since = (
            existing.active_since
            if existing is not None
            else datetime.now(timezone.utc).isoformat()
        )
        self._active_alarms[AlarmCode.DAC_COMMUNICATION_LOST] = AlarmState(
            code=AlarmCode.DAC_COMMUNICATION_LOST,
            severity=AlarmSeverity.CRITICAL,
            message=self.DAC_ALARM_MESSAGE,
            active_since=active_since,
            last_error=error,
            occurrences=self._consecutive_hardware_failures,
        )
        LOGGER.error("Alarm active: %s: %s", AlarmCode.DAC_COMMUNICATION_LOST, error)

    def _complete_safe_recovery(self) -> None:
        had_fault = bool(self._active_alarms) or self._recovery_required
        self._setpoints = FanSetpoints.stopped()
        self._mode = VentilationMode.STOP
        self._output_state_known = True
        self._consecutive_hardware_failures = 0
        self._recovery_required = False
        self._active_alarms.clear()
        if had_fault:
            LOGGER.info("DAC communication recovered; outputs forced to 0 V and mode STOP")
