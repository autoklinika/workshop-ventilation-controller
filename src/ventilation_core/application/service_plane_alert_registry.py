from __future__ import annotations

import time
from threading import RLock
from typing import Any

from ventilation_core.application.alert_registry import AlertRegistry
from ventilation_core.domain.alerts import AlertRecord, AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity, AlarmState
from ventilation_core.service_plane_monitor import ServicePlaneMonitor, ServicePlaneMonitorState


class ServicePlaneCorrelatingAlertRegistry:
    """Correlate independent WVC-SERVICE facts with existing core alerts.

    The wrapped registry remains the authoritative lifecycle/persistence owner.
    This layer only transforms the set of diagnostic signals before reconcile.
    It never executes AlertV2 reactions and never calls a control method.
    """

    def __init__(
        self,
        delegate: AlertRegistry,
        monitor: ServicePlaneMonitor,
        *,
        agent_failure_threshold: int = 3,
        node_initial_grace_seconds: float = 40.0,
    ) -> None:
        if isinstance(agent_failure_threshold, bool) or agent_failure_threshold < 1:
            raise ValueError("service agent failure threshold must be positive")
        if node_initial_grace_seconds < 0:
            raise ValueError("node initial grace must not be negative")
        self._delegate = delegate
        self._monitor = monitor
        self._agent_failure_threshold = int(agent_failure_threshold)
        self._node_initial_grace_ms = int(node_initial_grace_seconds * 1000)
        self._lock = RLock()
        self._last_correlation: dict[str, Any] = {
            "mode": "read_only",
            "derived_codes": [],
            "suppressed_legacy_keys": [],
            "reason": "not_evaluated",
        }

    @property
    def monitor(self) -> ServicePlaneMonitor:
        return self._monitor

    def reconcile(
        self,
        signals: tuple[AlertSignal, ...] | list[AlertSignal],
    ) -> tuple[AlertRecord, ...]:
        monitor_state = self._monitor.poll()
        correlated, diagnostics = self._correlate(tuple(signals), monitor_state)
        with self._lock:
            self._last_correlation = diagnostics
        return self._delegate.reconcile(list(correlated))

    def activate(self, signal: AlertSignal) -> AlertRecord:
        return self._delegate.activate(signal)

    def clear_key(self, key: str) -> AlertRecord | None:
        return self._delegate.clear_key(key)

    def acknowledge(self, alert_id: int) -> AlertRecord:
        return self._delegate.acknowledge(alert_id)

    def active_records(self) -> tuple[AlertRecord, ...]:
        return self._delegate.active_records()

    def active_alarm_states(self) -> tuple[AlarmState, ...]:
        return self._delegate.active_alarm_states()

    def history(self, limit: int = 200) -> tuple[AlertRecord, ...]:
        return self._delegate.history(limit)

    def close(self) -> None:
        self._delegate.close()

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            correlation = dict(self._last_correlation)
        return {
            "monitor": self._monitor.state().to_dict(),
            "correlation": correlation,
            "control_policy_applied": False,
        }

    def _correlate(
        self,
        base_signals: tuple[AlertSignal, ...],
        monitor_state: ServicePlaneMonitorState,
    ) -> tuple[tuple[AlertSignal, ...], dict[str, Any]]:
        signals = list(base_signals)
        derived: list[AlertSignal] = []
        suppressed: set[str] = set()

        if not monitor_state.available:
            if monitor_state.consecutive_failures >= self._agent_failure_threshold:
                derived.append(
                    AlertSignal(
                        key="service-plane:agent",
                        code=AlarmCode.SERVICE_AGENT_UNAVAILABLE,
                        source="service_agent",
                        severity=AlarmSeverity.WARNING,
                        message="CM5 Service Agent jest niedostępny",
                        detail=monitor_state.last_error or "Brak odpowiedzi lokalnego Service Agent",
                        occurrences=monitor_state.consecutive_failures,
                    )
                )
            diagnostics = self._diagnostics(
                derived,
                suppressed,
                reason="service_agent_unavailable",
            )
            return tuple(signals + derived), diagnostics

        snapshot = monitor_state.snapshot
        if not isinstance(snapshot, dict):
            diagnostics = self._diagnostics(derived, suppressed, reason="snapshot_unavailable")
            return tuple(signals), diagnostics

        network = snapshot.get("network")
        if not isinstance(network, dict):
            diagnostics = self._diagnostics(derived, suppressed, reason="network_snapshot_invalid")
            return tuple(signals), diagnostics

        ap_ok = network.get("ap_active") is True and network.get("address_present") is True
        dhcp_ok = network.get("dhcp_active") is True
        firewall_ok = network.get("firewall_active") is True

        if not ap_ok:
            derived.append(
                AlertSignal(
                    key="service-plane:network:ap",
                    code=AlarmCode.SERVICE_NETWORK_AP_UNAVAILABLE,
                    source="service_network",
                    severity=AlarmSeverity.WARNING,
                    message="Sieć WVC-SERVICE nie jest gotowa",
                    detail=(
                        f"ap_active={network.get('ap_active')!r}, "
                        f"address_present={network.get('address_present')!r}"
                    ),
                )
            )
        if not dhcp_ok:
            derived.append(
                AlertSignal(
                    key="service-plane:network:dhcp",
                    code=AlarmCode.SERVICE_NETWORK_DHCP_UNAVAILABLE,
                    source="service_network",
                    severity=AlarmSeverity.WARNING,
                    message="DHCP WVC-SERVICE jest niedostępny",
                    detail=f"dhcp_active={network.get('dhcp_active')!r}",
                )
            )
        if not firewall_ok:
            derived.append(
                AlertSignal(
                    key="service-plane:network:firewall",
                    code=AlarmCode.SERVICE_NETWORK_FIREWALL_INVALID,
                    source="service_network",
                    severity=AlarmSeverity.WARNING,
                    message="Firewall WVC-SERVICE nie jest w oczekiwanym stanie",
                    detail=f"firewall_active={network.get('firewall_active')!r}",
                )
            )

        # If the service network itself is unhealthy, heartbeat absence cannot be
        # attributed to a KAmod node. Preserve independent production SENSOR BUS
        # alerts and report only the service-plane cause.
        if not (ap_ok and dhcp_ok and firewall_ok):
            diagnostics = self._diagnostics(
                derived,
                suppressed,
                reason="service_network_degraded_node_correlation_suspended",
            )
            return tuple(signals + derived), diagnostics

        production_by_address: dict[int, list[AlertSignal]] = {}
        for signal in signals:
            if signal.code not in {
                AlarmCode.SENSOR_NODE_UNAVAILABLE,
                AlarmCode.SENSOR_DATA_INVALID,
            }:
                continue
            address = self._source_address(signal.source)
            if address is not None:
                production_by_address.setdefault(address, []).append(signal)

        agent = snapshot.get("agent")
        agent_started_ms = agent.get("started_unix_ms") if isinstance(agent, dict) else None
        now_ms = int(time.time() * 1000)
        agent_grace_elapsed = (
            isinstance(agent_started_ms, int)
            and now_ms - agent_started_ms >= self._node_initial_grace_ms
        )

        nodes = snapshot.get("nodes")
        if not isinstance(nodes, list):
            nodes = []
        for raw_node in nodes:
            if not isinstance(raw_node, dict):
                continue
            node_id = raw_node.get("node_id")
            if not isinstance(node_id, str) or not node_id:
                continue
            address = raw_node.get("modbus_address")
            if isinstance(address, bool) or not isinstance(address, int) or not 1 <= address <= 247:
                address = None
            production_faults = production_by_address.get(address, []) if address is not None else []
            production_failed = bool(production_faults)
            source = f"sensor:{address}" if address is not None else f"service-node:{node_id}"

            if raw_node.get("online") is not True:
                received_ms = raw_node.get("received_unix_ms")
                heartbeat_absence_mature = isinstance(received_ms, int) or agent_grace_elapsed
                if not heartbeat_absence_mature:
                    continue
                if production_failed and address is not None:
                    for fault in production_faults:
                        suppressed.add(fault.key)
                    derived.append(
                        AlertSignal(
                            key=f"sensor-node:{address}:correlated-unavailable",
                            code=AlarmCode.KAMOD_NODE_UNAVAILABLE,
                            source=source,
                            severity=AlarmSeverity.WARNING,
                            message=f"Węzeł KAmod/SEN55 {address} jest niedostępny",
                            detail=(
                                f"SENSOR BUS zgłasza problem i niezależny heartbeat {node_id} jest offline"
                            ),
                        )
                    )
                else:
                    derived.append(
                        AlertSignal(
                            key=f"service-node:{node_id}:heartbeat",
                            code=AlarmCode.KAMOD_HEARTBEAT_LOST,
                            source=source,
                            severity=AlarmSeverity.WARNING,
                            message=f"Brak heartbeat KAmod {node_id}",
                            detail="Produkcyjny SENSOR BUS nie potwierdza równoczesnej awarii węzła",
                        )
                    )
                continue

            # Explicit local diagnostics are used as a root-cause hint only when
            # the independent production path also reports a problem. This avoids
            # raising an alarm from one stale 10 s heartbeat snapshot.
            if not production_failed or address is None:
                continue

            sensor_state = raw_node.get("sensor_state")
            if sensor_state == "offline":
                for fault in production_faults:
                    suppressed.add(fault.key)
                derived.append(
                    AlertSignal(
                        key=f"sensor-node:{address}:kamod-sensor-state",
                        code=AlarmCode.KAMOD_SENSOR_STATE_ERROR,
                        source=source,
                        severity=AlarmSeverity.WARNING,
                        message=f"KAmod {node_id} raportuje lokalny błąd SEN55",
                        detail="sensor_state=offline oraz produkcyjny SENSOR BUS potwierdza problem",
                    )
                )
                continue

            if raw_node.get("rs485_ready") is False:
                for fault in production_faults:
                    suppressed.add(fault.key)
                derived.append(
                    AlertSignal(
                        key=f"sensor-node:{address}:kamod-rs485",
                        code=AlarmCode.KAMOD_RS485_NOT_READY,
                        source=source,
                        severity=AlarmSeverity.WARNING,
                        message=f"KAmod {node_id} nie potwierdza gotowości RS-485",
                        detail="rs485_ready=false oraz produkcyjny SENSOR BUS potwierdza problem",
                    )
                )

        if suppressed:
            signals = [signal for signal in signals if signal.key not in suppressed]

        diagnostics = self._diagnostics(derived, suppressed, reason="correlation_complete")
        return tuple(signals + derived), diagnostics

    @staticmethod
    def _source_address(source: str) -> int | None:
        if not source.startswith("sensor:"):
            return None
        try:
            address = int(source.split(":", 1)[1], 10)
        except (ValueError, IndexError):
            return None
        return address if 1 <= address <= 247 else None

    @staticmethod
    def _diagnostics(
        derived: list[AlertSignal],
        suppressed: set[str],
        *,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "mode": "read_only",
            "reason": reason,
            "derived_codes": [signal.code.value for signal in derived],
            "derived_keys": [signal.key for signal in derived],
            "suppressed_legacy_keys": sorted(suppressed),
            "control_policy_applied": False,
        }
