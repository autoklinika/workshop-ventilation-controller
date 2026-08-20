from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from ventilation_core.service_plane_monitor import (
    DEFAULT_SERVICE_AGENT_SOCKET,
    read_service_agent_status,
)

from .client import CoreClient, CoreClientError


DEFAULT_AI_SERVER_HOST = "192.168.1.55"
DEFAULT_AI_SERVER_PORT = 8080
DEFAULT_MQTT_HOST = "127.0.0.1"
DEFAULT_MQTT_PORT = 1883

SERVICE_UNITS = (
    "ventilation-core.service",
    "wvc-web-ui.service",
    "wvc-telemetry-sync.service",
    "wvc-service-agent.service",
    "zigbee2mqtt.service",
    "mosquitto.service",
    "wvc-weather.service",
    "wvc-ai-advisory.service",
)


class AdvisorySnapshotProvider(Protocol):
    def get_snapshot(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


CommandRunner = Callable[[tuple[str, ...], float], CommandResult]
ServiceAgentReader = Callable[[Path, float], dict[str, Any]]
TcpProbe = Callable[[str, int, float], bool]


def _run_command(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(1, "", str(exc))
    return CommandResult(
        int(completed.returncode),
        completed.stdout.strip(),
        completed.stderr.strip(),
    )


def _tcp_probe(host: str, port: int, timeout_seconds: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip("\x00\n ")
    except OSError:
        return None


def _safe_float(value: str | None, divisor: float = 1.0) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / divisor
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    text = _read_text(Path("/etc/os-release"))
    if text is None:
        return result
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def _parse_key_value_output(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


class ServiceStatusProvider:
    """Bounded, read-only diagnostics aggregation for the SERVICE Web UI.

    The provider has no control methods. It reads ventilation-core state, local
    Linux/sysfs/procfs diagnostics, fixed systemd properties, the independent
    Service Agent status socket and SQLite metadata using read-only connections.
    No shell is used and no command is constructed from browser input.
    """

    def __init__(
        self,
        core: CoreClient,
        *,
        telemetry_database: Path,
        alert_database: Path,
        advisory: AdvisorySnapshotProvider | None = None,
        service_agent_socket: Path = DEFAULT_SERVICE_AGENT_SOCKET,
        ai_server_host: str = DEFAULT_AI_SERVER_HOST,
        ai_server_port: int = DEFAULT_AI_SERVER_PORT,
        mqtt_host: str = DEFAULT_MQTT_HOST,
        mqtt_port: int = DEFAULT_MQTT_PORT,
        command_runner: CommandRunner | None = None,
        service_agent_reader: ServiceAgentReader | None = None,
        tcp_probe: TcpProbe | None = None,
    ) -> None:
        if not 1 <= ai_server_port <= 65535:
            raise ValueError("AI server port must be within 1..65535")
        if not 1 <= mqtt_port <= 65535:
            raise ValueError("MQTT port must be within 1..65535")
        self._core = core
        self._telemetry_database = Path(telemetry_database)
        self._alert_database = Path(alert_database)
        self._advisory = advisory
        self._service_agent_socket = Path(service_agent_socket)
        self._ai_server_host = ai_server_host
        self._ai_server_port = int(ai_server_port)
        self._mqtt_host = mqtt_host
        self._mqtt_port = int(mqtt_port)
        self._run = command_runner or _run_command
        self._service_agent_reader = service_agent_reader or read_service_agent_status
        self._tcp_probe = tcp_probe or _tcp_probe
        self._cpu_lock = threading.Lock()
        self._previous_cpu: tuple[int, int] | None = None

    def get_snapshot(self) -> dict[str, Any]:
        core = self._core_snapshot()
        system = self._system_snapshot()
        services = self._services_snapshot()
        service_plane = self._service_plane_snapshot()
        network = self._network_snapshot(service_plane)
        data = self._data_snapshot()
        ai = self._ai_snapshot(network)
        hardware = self._hardware_snapshot(core)
        summary = self._summary(
            system=system,
            core=core,
            hardware=hardware,
            services=services,
            network=network,
            data=data,
            ai=ai,
        )
        return {
            "available": True,
            "configured": True,
            "read_only": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "system": system,
            "services": services,
            "core": core,
            "hardware": hardware,
            "network": network,
            "data": data,
            "ai": ai,
        }

    def _core_snapshot(self) -> dict[str, Any]:
        try:
            status = self._core.request({"command": "status"})
        except CoreClientError as exc:
            return {"available": False, "error": str(exc), "active_alert_count": None}

        state = status.get("state")
        if status.get("ok") is not True or not isinstance(state, dict):
            return {
                "available": False,
                "error": str(status.get("error") or "invalid ventilation-core status"),
                "active_alert_count": None,
            }

        active_alert_count: int | None = None
        critical_alert_count: int | None = None
        try:
            alerts = self._core.request({"command": "alerts", "limit": 1})
        except CoreClientError:
            alerts = {}
        active = alerts.get("active")
        if alerts.get("ok") is True and isinstance(active, list):
            active_alert_count = len(active)
            critical_alert_count = sum(
                1 for alert in active
                if isinstance(alert, dict) and alert.get("severity") == "critical"
            )

        alert_v2 = state.get("alert_v2")
        if not isinstance(alert_v2, dict):
            alert_v2 = {}

        return {
            "available": True,
            "mode": state.get("mode"),
            "setpoints": state.get("setpoints"),
            "hardware_ready": state.get("hardware_ready"),
            "output_state_known": state.get("output_state_known"),
            "consecutive_hardware_failures": state.get("consecutive_hardware_failures"),
            "active_alert_count": active_alert_count,
            "critical_alert_count": critical_alert_count,
            "alert_v2": {
                "policy_version": alert_v2.get("policy_version"),
                "policy_sha256": alert_v2.get("policy_sha256"),
                "control_policy_applied": alert_v2.get("control_policy_applied"),
                "highest_active_weight": alert_v2.get("highest_active_weight"),
                "hmi_color": alert_v2.get("hmi_color"),
            },
            "raw_state": state,
        }

    def _system_snapshot(self) -> dict[str, Any]:
        os_release = _parse_os_release()
        uptime_text = _read_text(Path("/proc/uptime"))
        uptime_seconds = _safe_float(uptime_text.split()[0] if uptime_text else None)
        memory = self._memory_snapshot()
        root_storage = self._filesystem_snapshot(Path("/"))
        try:
            load = os.getloadavg()
        except (AttributeError, OSError):
            load = (None, None, None)
        return {
            "model": _read_text(Path("/proc/device-tree/model")) or platform.machine(),
            "hostname": socket.gethostname(),
            "os": os_release.get("PRETTY_NAME") or platform.platform(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "uptime_seconds": uptime_seconds,
            "load_average": {
                "1m": load[0],
                "5m": load[1],
                "15m": load[2],
            },
            "cpu_usage_percent": self._cpu_usage_percent(),
            "cpu_temperature_celsius": self._cpu_temperature(),
            "memory": memory,
            "root_storage": root_storage,
            "power": self._power_snapshot(),
            "system_time": datetime.now(timezone.utc).isoformat(),
        }

    def _cpu_usage_percent(self) -> float | None:
        text = _read_text(Path("/proc/stat"))
        if text is None:
            return None
        first = text.splitlines()[0].split()
        if len(first) < 5 or first[0] != "cpu":
            return None
        try:
            values = [int(value) for value in first[1:]]
        except ValueError:
            return None
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        with self._cpu_lock:
            previous = self._previous_cpu
            self._previous_cpu = (total, idle)
        if previous is None:
            return None
        total_delta = total - previous[0]
        idle_delta = idle - previous[1]
        if total_delta <= 0:
            return None
        busy = max(0, total_delta - idle_delta)
        return round(100.0 * busy / total_delta, 1)

    @staticmethod
    def _cpu_temperature() -> float | None:
        candidates = (
            Path("/sys/class/thermal/thermal_zone0/temp"),
            Path("/sys/devices/virtual/thermal/thermal_zone0/temp"),
        )
        for path in candidates:
            value = _safe_float(_read_text(path), 1000.0)
            if value is not None:
                return round(value, 1)
        return None

    @staticmethod
    def _memory_snapshot() -> dict[str, Any]:
        text = _read_text(Path("/proc/meminfo"))
        values: dict[str, int] = {}
        if text:
            for line in text.splitlines():
                key, sep, rest = line.partition(":")
                if not sep:
                    continue
                token = rest.strip().split()[0] if rest.strip() else ""
                try:
                    values[key] = int(token) * 1024
                except ValueError:
                    continue
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        used = None if total is None or available is None else max(0, total - available)
        used_percent = None
        if total and used is not None:
            used_percent = round(100.0 * used / total, 1)
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "used_percent": used_percent,
        }

    @staticmethod
    def _filesystem_snapshot(path: Path) -> dict[str, Any]:
        try:
            usage = shutil.disk_usage(path)
        except OSError as exc:
            return {"available": False, "error": str(exc)}
        used = usage.total - usage.free
        return {
            "available": True,
            "path": str(path),
            "total_bytes": usage.total,
            "used_bytes": used,
            "free_bytes": usage.free,
            "used_percent": round(100.0 * used / usage.total, 1) if usage.total else None,
        }

    def _power_snapshot(self) -> dict[str, Any]:
        result = self._run(("/usr/bin/vcgencmd", "get_throttled"), 0.6)
        raw = result.stdout.strip()
        prefix = "throttled=0x"
        if result.returncode != 0 or not raw.startswith(prefix):
            return {
                "available": False,
                "raw": raw or None,
                "mask": None,
                "undervoltage_now": None,
                "undervoltage_occurred": None,
                "throttled_now": None,
                "throttled_occurred": None,
                "error": result.stderr or "vcgencmd get_throttled unavailable",
            }
        try:
            mask = int(raw[len(prefix):], 16)
        except ValueError:
            return {
                "available": False,
                "raw": raw,
                "mask": None,
                "undervoltage_now": None,
                "undervoltage_occurred": None,
                "throttled_now": None,
                "throttled_occurred": None,
                "error": "invalid get_throttled output",
            }
        return {
            "available": True,
            "raw": raw,
            "mask": mask,
            "mask_hex": f"0x{mask:x}",
            "undervoltage_now": bool(mask & (1 << 0)),
            "undervoltage_occurred": bool(mask & (1 << 16)),
            "throttled_now": bool(mask & (1 << 2)),
            "throttled_occurred": bool(mask & (1 << 18)),
            "error": None,
        }

    def _services_snapshot(self) -> list[dict[str, Any]]:
        return [self._service_snapshot(unit) for unit in SERVICE_UNITS]

    def _service_snapshot(self, unit: str) -> dict[str, Any]:
        result = self._run(
            (
                "/usr/bin/systemctl",
                "show",
                unit,
                "--no-pager",
                "--property=LoadState,ActiveState,SubState,MainPID,NRestarts,ActiveEnterTimestampMonotonic,ExecMainStartTimestamp",
            ),
            0.8,
        )
        values = _parse_key_value_output(result.stdout)
        active_enter_us = _safe_int(values.get("ActiveEnterTimestampMonotonic"))
        uptime_seconds = None
        if active_enter_us and active_enter_us > 0:
            uptime_seconds = max(0.0, time.monotonic() - active_enter_us / 1_000_000.0)
        return {
            "unit": unit,
            "available": result.returncode == 0 and values.get("LoadState") != "not-found",
            "load_state": values.get("LoadState"),
            "active_state": values.get("ActiveState"),
            "sub_state": values.get("SubState"),
            "pid": _safe_int(values.get("MainPID")),
            "restarts": _safe_int(values.get("NRestarts")),
            "started_at": values.get("ExecMainStartTimestamp") or None,
            "uptime_seconds": round(uptime_seconds, 1) if uptime_seconds is not None else None,
            "error": None if result.returncode == 0 else (result.stderr or "systemctl show failed"),
        }

    def _service_plane_snapshot(self) -> dict[str, Any]:
        try:
            snapshot = self._service_agent_reader(self._service_agent_socket, 0.35)
        except Exception as exc:
            return {
                "available": False,
                "socket": str(self._service_agent_socket),
                "error": str(exc),
                "agent": None,
                "network": None,
                "nodes": [],
            }
        return {
            "available": True,
            "socket": str(self._service_agent_socket),
            "error": None,
            "agent": snapshot.get("agent"),
            "network": snapshot.get("network"),
            "nodes": snapshot.get("nodes") if isinstance(snapshot.get("nodes"), list) else [],
        }

    def _network_snapshot(self, service_plane: dict[str, Any]) -> dict[str, Any]:
        interfaces = self._network_interfaces()
        default_route: dict[str, Any] | None = None
        ip_result = self._run(("/usr/sbin/ip", "-j", "route", "show", "default"), 0.6)
        if ip_result.returncode != 0:
            ip_result = self._run(("/usr/bin/ip", "-j", "route", "show", "default"), 0.6)
        if ip_result.returncode == 0 and ip_result.stdout:
            try:
                routes = json.loads(ip_result.stdout)
                if isinstance(routes, list) and routes and isinstance(routes[0], dict):
                    route = routes[0]
                    default_route = {
                        "gateway": route.get("gateway"),
                        "interface": route.get("dev"),
                        "metric": route.get("metric"),
                    }
            except json.JSONDecodeError:
                pass

        ai_reachable = self._tcp_probe(self._ai_server_host, self._ai_server_port, 0.35)
        mqtt_reachable = self._tcp_probe(self._mqtt_host, self._mqtt_port, 0.25)
        return {
            "interfaces": interfaces,
            "default_route": default_route,
            "ai_server": {
                "host": self._ai_server_host,
                "port": self._ai_server_port,
                "reachable": ai_reachable,
            },
            "mqtt": {
                "host": self._mqtt_host,
                "port": self._mqtt_port,
                "reachable": mqtt_reachable,
            },
            "service_plane": service_plane,
        }

    def _network_interfaces(self) -> list[dict[str, Any]]:
        addresses: dict[str, list[str]] = {}
        ip_result = self._run(("/usr/sbin/ip", "-j", "address", "show"), 0.7)
        if ip_result.returncode != 0:
            ip_result = self._run(("/usr/bin/ip", "-j", "address", "show"), 0.7)
        if ip_result.returncode == 0 and ip_result.stdout:
            try:
                payload = json.loads(ip_result.stdout)
                if isinstance(payload, list):
                    for item in payload:
                        if not isinstance(item, dict):
                            continue
                        name = item.get("ifname")
                        if not isinstance(name, str):
                            continue
                        values: list[str] = []
                        for address in item.get("addr_info", []):
                            if not isinstance(address, dict) or address.get("family") != "inet":
                                continue
                            local = address.get("local")
                            prefixlen = address.get("prefixlen")
                            if isinstance(local, str):
                                values.append(f"{local}/{prefixlen}" if isinstance(prefixlen, int) else local)
                        addresses[name] = values
            except json.JSONDecodeError:
                pass

        result: list[dict[str, Any]] = []
        root = Path("/sys/class/net")
        try:
            names = sorted(path.name for path in root.iterdir() if path.name != "lo")
        except OSError:
            names = sorted(addresses)
        for name in names:
            base = root / name
            speed = _safe_int(_read_text(base / "speed"))
            result.append(
                {
                    "name": name,
                    "operstate": _read_text(base / "operstate"),
                    "mac": _read_text(base / "address"),
                    "mtu": _safe_int(_read_text(base / "mtu")),
                    "speed_mbps": speed if speed is None or speed >= 0 else None,
                    "ipv4": addresses.get(name, []),
                }
            )
        return result

    def _data_snapshot(self) -> dict[str, Any]:
        return {
            "telemetry": self._telemetry_database_snapshot(),
            "alerts": self._alert_database_snapshot(),
        }

    def _telemetry_database_snapshot(self) -> dict[str, Any]:
        base = self._database_file_snapshot(self._telemetry_database)
        if base.get("available") is not True:
            return base
        try:
            db = sqlite3.connect(
                f"file:{self._telemetry_database}?mode=ro",
                uri=True,
                timeout=1.0,
            )
            try:
                row = db.execute(
                    "SELECT COUNT(*), SUM(CASE WHEN synced_at IS NULL THEN 1 ELSE 0 END), "
                    "MAX(captured_at), MAX(synced_at) FROM telemetry_samples"
                ).fetchone()
                tables = {
                    str(value[0])
                    for value in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                rollups: dict[str, Any] = {}
                for resolution, table in (
                    ("1m", "telemetry_rollup_1m"),
                    ("15m", "telemetry_rollup_15m"),
                    ("1h", "telemetry_rollup_1h"),
                    ("1d", "telemetry_rollup_1d"),
                ):
                    if table not in tables:
                        rollups[resolution] = {"available": False, "latest_bucket": None}
                        continue
                    latest = db.execute(f"SELECT MAX(bucket_start) FROM {table}").fetchone()[0]
                    rollups[resolution] = {"available": True, "latest_bucket": latest}
            finally:
                db.close()
        except (OSError, sqlite3.Error) as exc:
            return {**base, "query_available": False, "error": str(exc)}
        total = int(row[0] or 0) if row else 0
        pending = int(row[1] or 0) if row else 0
        return {
            **base,
            "query_available": True,
            "samples": total,
            "pending_sync": pending,
            "last_sample_at": row[2] if row else None,
            "last_synced_at": row[3] if row else None,
            "rollups": rollups,
        }

    def _alert_database_snapshot(self) -> dict[str, Any]:
        base = self._database_file_snapshot(self._alert_database)
        if base.get("available") is not True:
            return base
        try:
            db = sqlite3.connect(
                f"file:{self._alert_database}?mode=ro",
                uri=True,
                timeout=1.0,
            )
            try:
                row = db.execute(
                    "SELECT COUNT(*), "
                    "SUM(CASE WHEN cleared_at IS NULL THEN 1 ELSE 0 END), "
                    "MAX(alert_id) FROM alerts"
                ).fetchone()
            finally:
                db.close()
        except (OSError, sqlite3.Error) as exc:
            return {**base, "query_available": False, "error": str(exc)}
        return {
            **base,
            "query_available": True,
            "records": int(row[0] or 0) if row else 0,
            "active_records": int(row[1] or 0) if row else 0,
            "latest_alert_id": _safe_int(row[2]) if row else None,
        }

    @staticmethod
    def _database_file_snapshot(path: Path) -> dict[str, Any]:
        try:
            stat = path.stat()
        except OSError as exc:
            return {"available": False, "path": str(path), "size_bytes": None, "error": str(exc)}
        return {
            "available": True,
            "path": str(path),
            "size_bytes": stat.st_size,
            "error": None,
        }

    def _ai_snapshot(self, network: dict[str, Any]) -> dict[str, Any]:
        advisory: dict[str, Any]
        if self._advisory is None:
            advisory = {
                "available": False,
                "configured": False,
                "fresh": False,
                "stale": True,
            }
        else:
            try:
                advisory = self._advisory.get_snapshot()
            except Exception as exc:
                advisory = {
                    "available": False,
                    "configured": True,
                    "fresh": False,
                    "stale": True,
                    "error": str(exc),
                }
        report = advisory.get("report") if isinstance(advisory, dict) else None
        return {
            "server_reachable": network.get("ai_server", {}).get("reachable"),
            "advisory_available": advisory.get("available") if isinstance(advisory, dict) else None,
            "advisory_fresh": advisory.get("fresh") if isinstance(advisory, dict) else None,
            "advisory_stale": advisory.get("stale") if isinstance(advisory, dict) else None,
            "advisory_age_seconds": advisory.get("age_seconds") if isinstance(advisory, dict) else None,
            "last_window_end": report.get("window_end") if isinstance(report, dict) else None,
            "error": advisory.get("error") if isinstance(advisory, dict) else None,
        }

    @staticmethod
    def _tacho_service_status(mode: Any, channel: Any) -> dict[str, str]:
        if not isinstance(channel, dict):
            return {"state": "unavailable", "text": "BRAK DANYCH"}
        valid = channel.get("valid")
        if mode == "STOP" and valid is False:
            return {"state": "idle", "text": "N/D — STOP"}
        if valid is True:
            return {"state": "ok", "text": "TAK"}
        if valid is False:
            return {"state": "warning", "text": "NIE"}
        return {"state": "unavailable", "text": "—"}

    @classmethod
    def _hardware_snapshot(cls, core: dict[str, Any]) -> dict[str, Any]:
        state = core.get("raw_state")
        if not isinstance(state, dict):
            return {
                "available": False,
                "sensor_bus": None,
                "sen55_nodes": [],
                "aero": None,
                "tacho": None,
                "zigbee": None,
            }
        sensor_bus = state.get("sensor_bus") if isinstance(state.get("sensor_bus"), dict) else None
        nodes = sensor_bus.get("nodes") if isinstance(sensor_bus, dict) else []
        sen55_nodes: list[dict[str, Any]] = []
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                sen55_nodes.append(
                    {
                        "slave_address": node.get("slave_address"),
                        "online": node.get("online"),
                        "usable": node.get("usable"),
                        "firmware_version": node.get("firmware_version"),
                        "last_success_at": node.get("last_success_at"),
                        "polls": node.get("polls"),
                        "successful_polls": node.get("successful_polls"),
                        "communication_errors": node.get("communication_errors"),
                        "consecutive_failures": node.get("consecutive_failures"),
                        "last_error": node.get("last_error"),
                    }
                )

        raw_tacho = state.get("tacho") if isinstance(state.get("tacho"), dict) else None
        tacho: dict[str, Any] | None = None
        if isinstance(raw_tacho, dict):
            tacho = dict(raw_tacho)
            mode = state.get("mode")
            for channel_name in ("supply", "extract"):
                raw_channel = raw_tacho.get(channel_name)
                if not isinstance(raw_channel, dict):
                    continue
                channel = dict(raw_channel)
                channel["service_status"] = cls._tacho_service_status(mode, raw_channel)
                tacho[channel_name] = channel

        return {
            "available": True,
            "sensor_bus": sensor_bus,
            "sen55_nodes": sen55_nodes,
            "aero": state.get("aero_bus") if isinstance(state.get("aero_bus"), dict) else None,
            "tacho": tacho,
            "zigbee": state.get("zigbee") if isinstance(state.get("zigbee"), dict) else None,
        }

    @staticmethod
    def _summary(
        *,
        system: dict[str, Any],
        core: dict[str, Any],
        hardware: dict[str, Any],
        services: list[dict[str, Any]],
        network: dict[str, Any],
        data: dict[str, Any],
        ai: dict[str, Any],
    ) -> list[dict[str, str]]:
        def state_from_bool(value: Any) -> str:
            if value is True:
                return "ok"
            if value is False:
                return "warning"
            return "unavailable"

        power = system.get("power") if isinstance(system.get("power"), dict) else {}
        if power.get("undervoltage_now") is True:
            system_state = "critical"
            system_detail = "Aktywny undervoltage"
        elif power.get("available") is True:
            system_state = "ok"
            system_detail = "Zasilanie bieżące OK"
        else:
            system_state = "unavailable"
            system_detail = "Brak diagnostyki zasilania"

        core_available = core.get("available") is True
        core_ready = core.get("hardware_ready") is True and core.get("output_state_known") is True
        if not core_available:
            core_state = "critical"
        elif core.get("critical_alert_count"):
            core_state = "critical"
        elif core_ready:
            core_state = "ok"
        else:
            core_state = "warning"

        sensor = hardware.get("sensor_bus") if isinstance(hardware.get("sensor_bus"), dict) else {}
        aero = hardware.get("aero") if isinstance(hardware.get("aero"), dict) else {}
        zigbee = hardware.get("zigbee") if isinstance(hardware.get("zigbee"), dict) else {}
        service_by_unit = {item.get("unit"): item for item in services}
        telemetry_service = service_by_unit.get("wvc-telemetry-sync.service", {})
        data_telemetry = data.get("telemetry") if isinstance(data.get("telemetry"), dict) else {}

        return [
            {"key": "system", "label": "SYSTEM", "state": system_state, "detail": system_detail},
            {"key": "core", "label": "CORE", "state": core_state, "detail": str(core.get("mode") or "—")},
            {"key": "dac", "label": "DAC", "state": state_from_bool(core.get("hardware_ready") is True and core.get("output_state_known") is True if core_available else None), "detail": "wyjścia znane" if core.get("output_state_known") is True else "stan niepewny"},
            {"key": "sensor_bus", "label": "SENSOR BUS", "state": state_from_bool(sensor.get("ready") is True and sensor.get("worker_alive") is True if sensor else None), "detail": f"{len(hardware.get('sen55_nodes', []))} SEN55"},
            {"key": "aero", "label": "AERO", "state": state_from_bool(aero.get("online") is True and aero.get("usable") is True if aero else None), "detail": "Modbus"},
            {"key": "zigbee", "label": "ZIGBEE", "state": state_from_bool(zigbee.get("connected") if zigbee else None), "detail": str(zigbee.get("broker_host") or "MQTT")},
            {"key": "ai", "label": "AI SERVER", "state": state_from_bool(ai.get("server_reachable")), "detail": "advisory fresh" if ai.get("advisory_fresh") is True else "połączenie"},
            {"key": "telemetry", "label": "TELEMETRIA", "state": state_from_bool(telemetry_service.get("active_state") == "active" if telemetry_service else None), "detail": f"pending: {data_telemetry.get('pending_sync', '—')}"},
        ]
