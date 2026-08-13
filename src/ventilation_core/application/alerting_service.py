from __future__ import annotations

from dataclasses import replace

from ventilation_core.application.alert_registry import AlertRegistry
from ventilation_core.application.service import VentilationService
from ventilation_core.domain.alerts import AlertRecord, AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity, CoreState


class AlertingVentilationService(VentilationService):
    """VentilationService with core-owned persistent system alert lifecycle."""

    def __init__(
        self,
        *args: object,
        alert_registry: AlertRegistry,
        required_tacho_channels: tuple[str, ...] = (),
        **kwargs: object,
    ) -> None:
        unsupported = set(required_tacho_channels) - {"supply", "extract"}
        if unsupported:
            raise ValueError(f"Unsupported required TACHO channels: {sorted(unsupported)}")
        self._system_alerts = alert_registry
        self._required_tacho_channels = tuple(required_tacho_channels)
        super().__init__(*args, **kwargs)
        self._sync_dac_only(super().state())

    def state(self) -> CoreState:
        return self._with_system_alerts(super().state())

    def health_check(self) -> CoreState:
        super().health_check()
        raw = super().state()
        self._sync_alerts(raw)
        return self._with_system_alerts(raw)

    def set_manual(self, supply_voltage: float, extract_voltage: float) -> CoreState:
        try:
            super().set_manual(supply_voltage, extract_voltage)
        except Exception:
            self._sync_alerts(super().state())
            raise
        raw = super().state()
        self._sync_alerts(raw)
        return self._with_system_alerts(raw)

    def stop(self) -> CoreState:
        try:
            super().stop()
        except Exception:
            self._sync_alerts(super().state())
            raise
        raw = super().state()
        self._sync_alerts(raw)
        return self._with_system_alerts(raw)

    def active_alerts(self) -> tuple[AlertRecord, ...]:
        return self._system_alerts.active_records()

    def alert_history(self, limit: int = 200) -> tuple[AlertRecord, ...]:
        return self._system_alerts.history(limit)

    def acknowledge_alert(self, alert_id: int) -> AlertRecord:
        return self._system_alerts.acknowledge(alert_id)

    def close(self) -> None:
        try:
            super().close()
        finally:
            self._system_alerts.close()

    def _with_system_alerts(self, state: CoreState) -> CoreState:
        return replace(state, active_alarms=self._system_alerts.active_alarm_states())

    def _sync_dac_only(self, state: CoreState) -> None:
        for alarm in state.active_alarms:
            self._system_alerts.activate(
                AlertSignal(
                    key=f"core:{alarm.code.value}",
                    code=alarm.code,
                    source="dac",
                    severity=alarm.severity,
                    message=alarm.message,
                    detail=alarm.last_error,
                    occurrences=alarm.occurrences,
                )
            )

    def _sync_alerts(self, state: CoreState) -> None:
        signals: list[AlertSignal] = []
        for alarm in state.active_alarms:
            signals.append(
                AlertSignal(
                    key=f"core:{alarm.code.value}",
                    code=alarm.code,
                    source="dac",
                    severity=alarm.severity,
                    message=alarm.message,
                    detail=alarm.last_error,
                    occurrences=alarm.occurrences,
                )
            )

        critical_dac_active = any(
            alarm.code == AlarmCode.DAC_COMMUNICATION_LOST
            for alarm in state.active_alarms
        )
        if (
            not critical_dac_active
            and (
                state.hardware_ready is not True
                or state.output_state_known is not True
                or state.consecutive_hardware_failures > 0
            )
        ):
            signals.append(
                AlertSignal(
                    key="core:DAC_STATE_UNCERTAIN",
                    code=AlarmCode.DAC_STATE_UNCERTAIN,
                    source="dac",
                    severity=AlarmSeverity.WARNING,
                    message="Stan wyjść DAC nie jest potwierdzony",
                    detail="Oczekiwanie na bezpieczne odzyskanie komunikacji z DAC",
                    occurrences=max(1, state.consecutive_hardware_failures),
                )
            )

        sensor_bus = state.sensor_bus
        if sensor_bus is not None:
            if sensor_bus.worker_alive is not True or (
                sensor_bus.ready is not True and bool(sensor_bus.last_error)
            ):
                signals.append(
                    AlertSignal(
                        key="sensor-bus:health",
                        code=AlarmCode.SENSOR_BUS_UNAVAILABLE,
                        source="sensor_bus",
                        severity=AlarmSeverity.WARNING,
                        message="SENSOR BUS nie działa poprawnie",
                        detail=sensor_bus.last_error or "",
                        occurrences=max(1, sensor_bus.worker_restarts),
                    )
                )
            for node in sensor_bus.nodes:
                if (
                    node.polls >= 3
                    and node.consecutive_failures >= 3
                    and (node.online is not True or node.usable is not True)
                ):
                    signals.append(
                        AlertSignal(
                            key=f"sensor-node:{node.slave_address}:communication",
                            code=AlarmCode.SENSOR_NODE_UNAVAILABLE,
                            source=f"sensor:{node.slave_address}",
                            severity=AlarmSeverity.WARNING,
                            message=f"Czujnik SEN55 {node.slave_address}: brak poprawnej komunikacji",
                            detail=node.last_error or "",
                            occurrences=node.consecutive_failures,
                        )
                    )
                    continue
                if node.polls >= 3 and node.online is True and (
                    (node.measurement_stale is True and node.stale_measurements >= 3)
                    or (node.measurement_valid is not True and node.invalid_measurements >= 3)
                ):
                    signals.append(
                        AlertSignal(
                            key=f"sensor-node:{node.slave_address}:data",
                            code=AlarmCode.SENSOR_DATA_INVALID,
                            source=f"sensor:{node.slave_address}",
                            severity=AlarmSeverity.WARNING,
                            message=f"Czujnik SEN55 {node.slave_address}: dane pomiarowe są nieprawidłowe",
                            detail=node.last_error or "",
                            occurrences=max(1, node.stale_measurements, node.invalid_measurements),
                        )
                    )

        aero = state.aero_bus
        if aero is not None:
            aero_bad = (
                aero.worker_alive is not True
                or (
                    aero.consecutive_failures >= 3
                    and (aero.online is not True or aero.usable is not True)
                )
                or (aero.ready is not True and bool(aero.last_error))
            )
            if aero_bad:
                signals.append(
                    AlertSignal(
                        key="aero-bus:communication",
                        code=AlarmCode.AERO_BUS_UNAVAILABLE,
                        source="aero_bus",
                        severity=AlarmSeverity.WARNING,
                        message="Rekuperator AERO: brak poprawnej komunikacji",
                        detail=aero.last_error or "",
                        occurrences=max(1, aero.consecutive_failures),
                    )
                )

        tacho = state.tacho
        if tacho is not None:
            if tacho.worker_alive is not True or bool(tacho.last_error):
                signals.append(
                    AlertSignal(
                        key="tacho:monitor",
                        code=AlarmCode.TACHO_MONITOR_UNAVAILABLE,
                        source="tacho",
                        severity=AlarmSeverity.WARNING,
                        message="Monitor TACHO nie działa poprawnie",
                        detail=tacho.last_error or "",
                    )
                )
            for channel in self._required_tacho_channels:
                if getattr(tacho, channel) is None:
                    signals.append(
                        AlertSignal(
                            key=f"tacho:configuration:{channel}",
                            code=AlarmCode.TACHO_CONFIGURATION_INVALID,
                            source=f"tacho:{channel}",
                            severity=AlarmSeverity.WARNING,
                            message=f"Brak wymaganego kanału TACHO: {channel.upper()}",
                        )
                    )
        elif self._required_tacho_channels:
            for channel in self._required_tacho_channels:
                signals.append(
                    AlertSignal(
                        key=f"tacho:configuration:{channel}",
                        code=AlarmCode.TACHO_CONFIGURATION_INVALID,
                        source=f"tacho:{channel}",
                        severity=AlarmSeverity.WARNING,
                        message=f"Brak wymaganego monitora TACHO: {channel.upper()}",
                    )
                )

        self._system_alerts.reconcile(signals)
