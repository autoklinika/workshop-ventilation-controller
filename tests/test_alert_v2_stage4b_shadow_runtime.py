from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from ventilation_core.alert_v2_stage4b_runtime import (
    READ_ONLY_CORE_COMMANDS,
    CoreReadOnlyClient,
    Stage4BError,
    Stage4BShadowRuntime,
    active_payload_to_signal,
    require_passive_safe_state,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = REPO_ROOT / "config" / "alerts-v2.default.toml"


def _core_status(*, mode: str = "STOP", supply: float = 0.0, extract: float = 0.0) -> dict[str, Any]:
    return {
        "ok": True,
        "state": {
            "mode": mode,
            "setpoints": {
                "supply_voltage": supply,
                "extract_voltage": extract,
            },
            "output_state_known": True,
        },
    }


def _core_alerts() -> dict[str, Any]:
    return {
        "ok": True,
        "active": [
            {
                "alert_id": 60,
                "key": "aero:bus",
                "code": "AERO_BUS_UNAVAILABLE",
                "source": "aero_bus",
                "severity": "warning",
                "message": "AERO unavailable",
                "detail": "timeout",
                "active_since": "2026-08-19T00:00:00+00:00",
                "acknowledged": False,
                "acknowledged_at": None,
                "active": True,
                "cleared_at": None,
                "occurrences": 3,
            }
        ],
        "history": [],
    }


def _service_status() -> dict[str, Any]:
    return {
        "ok": True,
        "agent": {
            "ready": True,
            "started_unix_ms": 1,
            "registered_nodes": 2,
            "online_nodes": 2,
        },
        "network": {
            "ready": True,
            "ap_active": True,
            "address_present": True,
            "dhcp_active": True,
            "firewall_active": True,
        },
        "nodes": [
            {
                "node_id": "sensor-node-1",
                "online": True,
                "received_unix_ms": 1,
                "modbus_address": 1,
                "sensor_state": "running",
                "rs485_ready": True,
                "modbus_monitor_ready": True,
            },
            {
                "node_id": "sensor-node-2",
                "online": True,
                "received_unix_ms": 1,
                "modbus_address": 2,
                "sensor_state": "running",
                "rs485_ready": True,
                "modbus_monitor_ready": True,
            },
        ],
    }


class AlertV2Stage4BShadowRuntimeTests(unittest.TestCase):
    def test_core_read_boundary_has_only_status_and_alerts(self) -> None:
        self.assertEqual(READ_ONLY_CORE_COMMANDS, {"status", "alerts"})

    def test_core_client_rejects_control_command_before_transport(self) -> None:
        called = False

        def requester(_path: Path, _request: dict[str, Any], _timeout: float) -> dict[str, Any]:
            nonlocal called
            called = True
            return {"ok": True}

        client = CoreReadOnlyClient(Path("/unused"), requester=requester)
        with self.assertRaises(Stage4BError):
            client.request("set", supply_voltage=3.0, extract_voltage=3.0)
        self.assertFalse(called)

    def test_passive_safe_state_requires_stop_and_zero_volts(self) -> None:
        safe = require_passive_safe_state(_core_status())
        self.assertEqual(safe.mode, "STOP")
        self.assertEqual(safe.supply_voltage, 0.0)
        with self.assertRaises(Stage4BError):
            require_passive_safe_state(_core_status(mode="MANUAL", supply=2.0, extract=2.0))
        with self.assertRaises(Stage4BError):
            require_passive_safe_state(_core_status(supply=1.0))

    def test_active_alert_conversion_requires_lifecycle_key(self) -> None:
        payload = _core_alerts()["active"][0]
        signal = active_payload_to_signal(payload)
        self.assertEqual(signal.key, "aero:bus")
        self.assertEqual(signal.code.value, "AERO_BUS_UNAVAILABLE")
        bad = dict(payload)
        bad.pop("key")
        with self.assertRaises(Stage4BError):
            active_payload_to_signal(bad)

    def test_refresh_maps_live_alerts_without_control_or_persistent_store(self) -> None:
        core_commands: list[str] = []
        service_commands = 0

        def core_requester(
            _path: Path,
            request: dict[str, Any],
            _timeout: float,
        ) -> dict[str, Any]:
            command = str(request["command"])
            core_commands.append(command)
            if command == "status":
                return _core_status()
            if command == "alerts":
                return _core_alerts()
            raise AssertionError(f"unexpected command {command}")

        def service_requester(_path: Path, _timeout: float) -> dict[str, Any]:
            nonlocal service_commands
            service_commands += 1
            return _service_status()

        runtime = Stage4BShadowRuntime(
            policy_path=DEFAULT_POLICY,
            core_socket=Path("/unused/core.sock"),
            service_agent_socket=Path("/unused/service.sock"),
            core_requester=core_requester,
            service_requester=service_requester,
        )
        self.addCleanup(runtime.close)

        snapshot = runtime.refresh()

        self.assertEqual(core_commands, ["status", "alerts"])
        self.assertEqual(service_commands, 1)
        self.assertEqual(runtime.write_commands_sent, 0)
        self.assertFalse(snapshot["safety"]["control_policy_applied"])
        self.assertEqual(snapshot["policy"]["alert_count"], 50)
        self.assertEqual(snapshot["alert_v2"]["unmapped_active_alerts"], 0)
        self.assertEqual(snapshot["alert_v2"]["active_weight"], 3)
        self.assertEqual(snapshot["alert_v2"]["hmi_color"], "orange")
        self.assertEqual(snapshot["active"][0]["code"], "AERO_BUS_UNAVAILABLE")
        self.assertTrue(snapshot["active"][0]["alert_v2"]["mapped"])
        self.assertEqual(snapshot["correlation"]["reason"], "correlation_complete")
        self.assertFalse(snapshot["correlation"]["control_policy_applied"])

    def test_refresh_aborts_if_production_leaves_stop(self) -> None:
        def core_requester(
            _path: Path,
            request: dict[str, Any],
            _timeout: float,
        ) -> dict[str, Any]:
            if request["command"] == "status":
                return _core_status(mode="MANUAL", supply=2.0, extract=2.0)
            return _core_alerts()

        runtime = Stage4BShadowRuntime(
            policy_path=DEFAULT_POLICY,
            core_requester=core_requester,
            service_requester=lambda _path, _timeout: _service_status(),
        )
        self.addCleanup(runtime.close)
        with self.assertRaises(Stage4BError):
            runtime.refresh()


if __name__ == "__main__":
    unittest.main()
