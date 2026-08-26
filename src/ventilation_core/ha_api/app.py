from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ventilation_core.web.client import CoreClientError

from .client import ReadOnlyCore


@dataclass(frozen=True)
class HaResponse:
    status: int
    payload: dict[str, Any]


class HaReadOnlyApplication:
    """Minimal read-only HTTP application for Home Assistant.

    This boundary intentionally exposes no acknowledgement, schedule, Zigbee,
    fan, AERO, host-power or generic core command endpoint.  ``snapshot`` is a
    projection of the authoritative core status intended to keep Home Assistant
    configuration simple; it never evaluates control policy or sends commands.
    """

    def __init__(self, core: ReadOnlyCore) -> None:
        self._core = core

    def handle(self, method: str, path: str) -> HaResponse:
        if method != "GET":
            return HaResponse(405, {"ok": False, "error": "Method not allowed; HA API is read-only"})
        try:
            if path == "/api/ha/v1/state":
                return HaResponse(200, self._core.status())
            if path == "/api/ha/v1/snapshot":
                return self._snapshot()
            if path == "/api/ha/v1/alerts":
                return HaResponse(200, self._core.alerts(limit=200))
            if path == "/api/ha/v1/health":
                return self._health()
            return HaResponse(404, {"ok": False, "error": "Not found"})
        except (CoreClientError, OSError, TimeoutError) as exc:
            return HaResponse(503, {"ok": False, "error": str(exc)})

    def _snapshot(self) -> HaResponse:
        response = self._core.status()
        state = response["state"]

        sensor_bus = self._mapping(state.get("sensor_bus"))
        nodes: dict[str, dict[str, Any]] = {}
        raw_nodes = sensor_bus.get("nodes")
        if isinstance(raw_nodes, list):
            for node_value in raw_nodes:
                node = self._mapping(node_value)
                address = node.get("slave_address")
                if isinstance(address, bool) or not isinstance(address, int):
                    continue
                reading = self._mapping(node.get("reading"))
                nodes[str(address)] = {
                    "online": node.get("online"),
                    "usable": node.get("usable"),
                    "measurement_valid": node.get("measurement_valid"),
                    "measurement_stale": node.get("measurement_stale"),
                    "temperature_celsius": reading.get("temperature_celsius"),
                    "humidity_percent": reading.get("humidity_percent"),
                    "pm1_0_ug_m3": reading.get("pm1_0_ug_m3"),
                    "pm2_5_ug_m3": reading.get("pm2_5_ug_m3"),
                    "pm4_0_ug_m3": reading.get("pm4_0_ug_m3"),
                    "pm10_0_ug_m3": reading.get("pm10_0_ug_m3"),
                    "voc_index": reading.get("voc_index"),
                    "nox_index": reading.get("nox_index"),
                }

        tacho = self._mapping(state.get("tacho"))
        setpoints = self._mapping(state.get("setpoints"))
        aero = self._mapping(state.get("aero_bus"))
        aero_telemetry = self._mapping(aero.get("telemetry"))
        zigbee = self._mapping(state.get("zigbee"))
        alert_v2 = self._mapping(state.get("alert_v2"))

        active_items: list[dict[str, Any]] = []
        active_ids: list[int] = []
        raw_alerts = state.get("active_alarms")
        if isinstance(raw_alerts, list):
            for item_value in raw_alerts:
                item = self._mapping(item_value)
                if not item:
                    continue
                item_v2 = self._mapping(item.get("alert_v2"))
                alert_id = item.get("alert_id")
                if isinstance(alert_id, int) and not isinstance(alert_id, bool):
                    active_ids.append(alert_id)
                active_items.append(
                    {
                        "alert_id": alert_id,
                        "code": item.get("code"),
                        "source": item.get("source"),
                        "message": item.get("message"),
                        "active_since": item.get("active_since"),
                        "acknowledged": item.get("acknowledged"),
                        "weight": item_v2.get("weight"),
                        "severity": item_v2.get("severity", item.get("severity")),
                        "title": item_v2.get("title"),
                        "hmi_color": item_v2.get("hmi_color"),
                        "affects_control": item_v2.get("affects_control"),
                    }
                )

        return HaResponse(
            200,
            {
                "ok": True,
                "schema_version": 1,
                "read_only": True,
                "mode": state.get("mode"),
                "hardware_ready": state.get("hardware_ready"),
                "output_state_known": state.get("output_state_known"),
                "setpoints": {
                    "supply_voltage": setpoints.get("supply_voltage"),
                    "extract_voltage": setpoints.get("extract_voltage"),
                },
                "sensor_bus": {
                    "ready": sensor_bus.get("ready"),
                    "worker_alive": sensor_bus.get("worker_alive"),
                    "last_error": sensor_bus.get("last_error"),
                    "nodes": nodes,
                },
                "fans": {
                    "supply": self._tacho_channel(tacho.get("supply")),
                    "extract": self._tacho_channel(tacho.get("extract")),
                },
                "aero": {
                    "online": aero.get("online"),
                    "usable": aero.get("usable"),
                    "last_error": aero.get("last_error"),
                    "telemetry": aero_telemetry,
                },
                "zigbee": {
                    "running": zigbee.get("running"),
                    "connected": zigbee.get("connected"),
                    "bridge_online": zigbee.get("bridge_online"),
                    "last_error": zigbee.get("last_error"),
                },
                "alerts": {
                    "active_count": len(active_items),
                    "active_ids": sorted(active_ids),
                    "active_weight": alert_v2.get("active_weight"),
                    "hmi_color": alert_v2.get("hmi_color"),
                    "policy_version": alert_v2.get("policy_version"),
                    "control_policy_applied": alert_v2.get("control_policy_applied"),
                    "active": active_items,
                },
            },
        )

    def _health(self) -> HaResponse:
        try:
            self._core.status()
        except (CoreClientError, OSError, TimeoutError) as exc:
            return HaResponse(
                200,
                {
                    "ok": True,
                    "ha_api": "ok",
                    "read_only": True,
                    "core_available": False,
                    "core_error": str(exc),
                },
            )
        return HaResponse(
            200,
            {
                "ok": True,
                "ha_api": "ok",
                "read_only": True,
                "core_available": True,
            },
        )

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @classmethod
    def _tacho_channel(cls, value: Any) -> dict[str, Any]:
        channel = cls._mapping(value)
        return {
            "rpm": channel.get("rpm"),
            "valid": channel.get("valid"),
            "frequency_hz": channel.get("frequency_hz"),
        }
