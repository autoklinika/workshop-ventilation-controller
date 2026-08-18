from __future__ import annotations

import time
import unittest
from pathlib import Path
from typing import Any

from ventilation_core.application.alert_registry import AlertRegistry, MemoryAlertStore
from ventilation_core.application.service_plane_alert_registry import (
    ServicePlaneCorrelatingAlertRegistry,
)
from ventilation_core.domain.alerts import AlertSignal
from ventilation_core.domain.models import AlarmCode, AlarmSeverity
from ventilation_core.service_plane_monitor import ServicePlaneMonitor


def _sensor_unavailable(address: int = 1) -> AlertSignal:
    return AlertSignal(
        key=f"sensor-node:{address}:communication",
        code=AlarmCode.SENSOR_NODE_UNAVAILABLE,
        source=f"sensor:{address}",
        severity=AlarmSeverity.WARNING,
        message=f"sensor {address} unavailable",
        detail="modbus timeout",
        occurrences=3,
    )


def _tacho_warning() -> AlertSignal:
    return AlertSignal(
        key="tacho:monitor",
        code=AlarmCode.TACHO_MONITOR_UNAVAILABLE,
        source="tacho",
        severity=AlarmSeverity.WARNING,
        message="tacho unavailable",
    )


def _snapshot(
    *,
    node_online: bool = True,
    received_unix_ms: int | None = 1_000,
    sensor_state: str = "running",
    rs485_ready: bool = True,
    ap_active: bool = True,
    address_present: bool = True,
    dhcp_active: bool = True,
    firewall_active: bool = True,
    agent_age_ms: int = 60_000,
) -> dict[str, Any]:
    return {
        "ok": True,
        "agent": {
            "ready": True,
            "started_unix_ms": int(time.time() * 1000) - agent_age_ms,
            "registered_nodes": 1,
            "online_nodes": 1 if node_online else 0,
        },
        "network": {
            "ready": ap_active and address_present and dhcp_active and firewall_active,
            "ap_active": ap_active,
            "address_present": address_present,
            "dhcp_active": dhcp_active,
            "firewall_active": firewall_active,
        },
        "nodes": [
            {
                "node_id": "sensor-node-1",
                "online": node_online,
                "received_unix_ms": received_unix_ms,
                "modbus_address": 1,
                "sensor_state": sensor_state,
                "rs485_ready": rs485_ready,
                "modbus_monitor_ready": True,
            }
        ],
    }


class AlertV2ServicePlaneCorrelationTests(unittest.TestCase):
    def _registry_for(self, response: dict[str, Any]) -> ServicePlaneCorrelatingAlertRegistry:
        monitor = ServicePlaneMonitor(
            Path("/unused/service-agent.sock"),
            requester=lambda _path, _timeout: response,
        )
        return ServicePlaneCorrelatingAlertRegistry(
            AlertRegistry(MemoryAlertStore()),
            monitor,
            agent_failure_threshold=3,
            node_initial_grace_seconds=40.0,
        )

    def test_both_modbus_and_heartbeat_lost_become_one_correlated_node_alert(self) -> None:
        registry = self._registry_for(_snapshot(node_online=False))

        active = registry.reconcile([_sensor_unavailable()])

        self.assertEqual([record.code for record in active], [AlarmCode.KAMOD_NODE_UNAVAILABLE])
        diagnostics = registry.diagnostics()["correlation"]
        self.assertIn("sensor-node:1:communication", diagnostics["suppressed_legacy_keys"])
        self.assertEqual(diagnostics["derived_codes"], ["KAMOD_NODE_UNAVAILABLE"])

    def test_heartbeat_lost_but_production_healthy_is_service_only_warning(self) -> None:
        registry = self._registry_for(_snapshot(node_online=False))

        active = registry.reconcile([])

        self.assertEqual([record.code for record in active], [AlarmCode.KAMOD_HEARTBEAT_LOST])
        self.assertEqual(active[0].source, "sensor:1")

    def test_service_network_failure_prevents_false_node_correlation(self) -> None:
        registry = self._registry_for(
            _snapshot(node_online=False, ap_active=False, address_present=False)
        )

        active = registry.reconcile([_sensor_unavailable()])
        codes = {record.code for record in active}

        self.assertIn(AlarmCode.SENSOR_NODE_UNAVAILABLE, codes)
        self.assertIn(AlarmCode.SERVICE_NETWORK_AP_UNAVAILABLE, codes)
        self.assertNotIn(AlarmCode.KAMOD_NODE_UNAVAILABLE, codes)
        self.assertNotIn(AlarmCode.KAMOD_HEARTBEAT_LOST, codes)
        self.assertEqual(
            registry.diagnostics()["correlation"]["reason"],
            "service_network_degraded_node_correlation_suspended",
        )

    def test_local_sensor_offline_replaces_generic_modbus_symptom(self) -> None:
        registry = self._registry_for(_snapshot(sensor_state="offline"))

        active = registry.reconcile([_sensor_unavailable()])

        self.assertEqual([record.code for record in active], [AlarmCode.KAMOD_SENSOR_STATE_ERROR])
        self.assertIn("sensor_state=offline", active[0].detail)

    def test_local_rs485_not_ready_replaces_generic_modbus_symptom(self) -> None:
        registry = self._registry_for(_snapshot(rs485_ready=False))

        active = registry.reconcile([_sensor_unavailable()])

        self.assertEqual([record.code for record in active], [AlarmCode.KAMOD_RS485_NOT_READY])
        self.assertIn("rs485_ready=false", active[0].detail)

    def test_healthy_service_snapshot_does_not_hide_unexplained_production_failure(self) -> None:
        registry = self._registry_for(_snapshot())

        active = registry.reconcile([_sensor_unavailable()])

        self.assertEqual([record.code for record in active], [AlarmCode.SENSOR_NODE_UNAVAILABLE])
        self.assertEqual(registry.diagnostics()["correlation"]["derived_codes"], [])

    def test_initial_offline_registration_waits_for_grace_before_heartbeat_alert(self) -> None:
        registry = self._registry_for(
            _snapshot(
                node_online=False,
                received_unix_ms=None,
                agent_age_ms=10_000,
            )
        )

        active = registry.reconcile([])

        self.assertEqual(active, ())

    def test_service_agent_failure_alert_is_debounced_and_preserves_production_signal(self) -> None:
        def unavailable(_path: Path, _timeout: float) -> dict[str, Any]:
            raise TimeoutError("agent timeout")

        monitor = ServicePlaneMonitor(Path("/unused"), requester=unavailable)
        registry = ServicePlaneCorrelatingAlertRegistry(
            AlertRegistry(MemoryAlertStore()),
            monitor,
            agent_failure_threshold=3,
        )

        first = registry.reconcile([_sensor_unavailable()])
        second = registry.reconcile([_sensor_unavailable()])
        third = registry.reconcile([_sensor_unavailable()])

        self.assertEqual({record.code for record in first}, {AlarmCode.SENSOR_NODE_UNAVAILABLE})
        self.assertEqual({record.code for record in second}, {AlarmCode.SENSOR_NODE_UNAVAILABLE})
        self.assertEqual(
            {record.code for record in third},
            {AlarmCode.SENSOR_NODE_UNAVAILABLE, AlarmCode.SERVICE_AGENT_UNAVAILABLE},
        )

    def test_tacho_alert_passes_through_and_cannot_become_control_reaction_here(self) -> None:
        registry = self._registry_for(_snapshot())

        active = registry.reconcile([_tacho_warning()])

        self.assertEqual([record.code for record in active], [AlarmCode.TACHO_MONITOR_UNAVAILABLE])
        self.assertFalse(registry.diagnostics()["control_policy_applied"])


if __name__ == "__main__":
    unittest.main()
