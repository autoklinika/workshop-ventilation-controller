from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ventilation_core.web.alert_history_app import AlertHistoryWebApplication
from ventilation_core.web.service_status import CommandResult, ServiceStatusProvider


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


class FakeCore:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def request(self, payload: dict[str, object]) -> dict[str, object]:
        self.requests.append(dict(payload))
        if payload.get("command") == "alerts":
            return {
                "ok": True,
                "active": [
                    {
                        "alert_id": 9,
                        "severity": "warning",
                    }
                ],
                "history": [],
            }
        if payload.get("command") != "status":
            return {"ok": False, "error": "unsupported fake command"}
        return {
            "ok": True,
            "state": {
                "mode": "STOP",
                "setpoints": {
                    "supply_voltage": 0.0,
                    "extract_voltage": 0.0,
                },
                "hardware_ready": True,
                "output_state_known": True,
                "consecutive_hardware_failures": 0,
                "alert_v2": {
                    "policy_version": "2026-08-20.1",
                    "policy_sha256": "abc",
                    "control_policy_applied": False,
                    "highest_active_weight": 2,
                    "hmi_color": "yellow",
                },
                "sensor_bus": {
                    "port": "/dev/ttyAMA0",
                    "baudrate": 19200,
                    "ready": True,
                    "worker_alive": True,
                    "worker_restarts": 0,
                    "last_cycle_at": "2026-08-20T09:00:00+00:00",
                    "last_error": None,
                    "nodes": [
                        {
                            "slave_address": 1,
                            "online": True,
                            "usable": True,
                            "firmware_version": "0.6",
                            "last_success_at": "2026-08-20T09:00:00+00:00",
                            "polls": 100,
                            "successful_polls": 100,
                            "communication_errors": 0,
                            "consecutive_failures": 0,
                            "last_error": None,
                        }
                    ],
                },
                "aero_bus": {
                    "port": "/dev/ttyAMA4",
                    "baudrate": 9600,
                    "slave_address": 44,
                    "ready": True,
                    "worker_alive": True,
                    "online": True,
                    "usable": True,
                    "communication_errors": 0,
                    "last_success_at": "2026-08-20T09:00:00+00:00",
                },
                "tacho": {
                    "ready": True,
                    "worker_alive": True,
                    "supply": {
                        "line_name": "GPIO17",
                        "frequency_hz": 0.0,
                        "rpm": 0.0,
                        "valid": False,
                    },
                    "extract": {
                        "line_name": "GPIO27",
                        "frequency_hz": 0.0,
                        "rpm": 0.0,
                        "valid": False,
                    },
                },
                "zigbee": {
                    "broker_host": "127.0.0.1",
                    "broker_port": 1883,
                    "connected": True,
                    "bridge_online": True,
                    "inventory": [],
                    "sensor_list": [],
                },
            },
        }


class FakeAdvisory:
    def get_snapshot(self) -> dict[str, object]:
        return {
            "available": True,
            "configured": True,
            "fresh": True,
            "stale": False,
            "age_seconds": 60,
            "report": {"window_end": "2026-08-20T09:00:00+00:00"},
        }


class FakeServiceProvider:
    def get_snapshot(self) -> dict[str, object]:
        return {
            "available": True,
            "configured": True,
            "read_only": True,
            "summary": [],
        }


class ServiceDashboardStage1Test(unittest.TestCase):
    def _create_telemetry_db(self, path: Path) -> None:
        db = sqlite3.connect(path)
        db.executescript(
            """
            CREATE TABLE telemetry_samples (
                sequence INTEGER PRIMARY KEY,
                captured_at TEXT NOT NULL,
                synced_at TEXT
            );
            CREATE TABLE telemetry_rollup_1m (
                bucket_start TEXT PRIMARY KEY
            );
            CREATE TABLE telemetry_rollup_15m (
                bucket_start TEXT PRIMARY KEY
            );
            """
        )
        db.execute(
            "INSERT INTO telemetry_samples(sequence,captured_at,synced_at) VALUES (1,?,NULL)",
            ("2026-08-20T08:59:00+00:00",),
        )
        db.execute(
            "INSERT INTO telemetry_samples(sequence,captured_at,synced_at) VALUES (2,?,?)",
            ("2026-08-20T09:00:00+00:00", "2026-08-20T09:00:05+00:00"),
        )
        db.execute(
            "INSERT INTO telemetry_rollup_1m(bucket_start) VALUES (?)",
            ("2026-08-20T09:00:00+00:00",),
        )
        db.execute(
            "INSERT INTO telemetry_rollup_15m(bucket_start) VALUES (?)",
            ("2026-08-20T09:00:00+00:00",),
        )
        db.commit()
        db.close()

    def _create_alert_db(self, path: Path) -> None:
        db = sqlite3.connect(path)
        db.executescript(
            """
            CREATE TABLE alerts (
                alert_id INTEGER PRIMARY KEY,
                cleared_at TEXT
            );
            """
        )
        db.execute("INSERT INTO alerts(alert_id,cleared_at) VALUES (1,NULL)")
        db.execute(
            "INSERT INTO alerts(alert_id,cleared_at) VALUES (2,?)",
            ("2026-08-20T09:00:00+00:00",),
        )
        db.commit()
        db.close()

    def test_service_status_provider_collects_read_only_system_core_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            telemetry = Path(tempdir) / "telemetry.sqlite3"
            alerts = Path(tempdir) / "alerts.sqlite3"
            self._create_telemetry_db(telemetry)
            self._create_alert_db(alerts)
            commands: list[tuple[str, ...]] = []

            def command_runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
                self.assertGreater(timeout_seconds, 0)
                commands.append(command)
                if command == ("/usr/bin/vcgencmd", "get_throttled"):
                    return CommandResult(0, "throttled=0x50000")
                if len(command) >= 2 and command[0] == "/usr/bin/systemctl" and command[1] == "show":
                    return CommandResult(
                        0,
                        "\n".join(
                            (
                                "LoadState=loaded",
                                "ActiveState=active",
                                "SubState=running",
                                "MainPID=123",
                                "NRestarts=0",
                                "ActiveEnterTimestampMonotonic=1",
                                "ExecMainStartTimestamp=Thu 2026-08-20 09:00:00 CEST",
                            )
                        ),
                    )
                if command[-4:] == ("route", "show", "default"):
                    return CommandResult(0, json.dumps([{"gateway": "192.168.1.1", "dev": "eth0"}]))
                if command[-3:] == ("address", "show"):
                    return CommandResult(
                        0,
                        json.dumps(
                            [
                                {
                                    "ifname": "eth0",
                                    "addr_info": [
                                        {"family": "inet", "local": "192.168.1.64", "prefixlen": 24}
                                    ],
                                }
                            ]
                        ),
                    )
                return CommandResult(1, "", "not available in fake")

            def service_agent_reader(path: Path, timeout_seconds: float) -> dict[str, object]:
                self.assertGreater(timeout_seconds, 0)
                return {
                    "ok": True,
                    "agent": {
                        "ready": True,
                        "registered_nodes": 2,
                        "online_nodes": 2,
                    },
                    "network": {
                        "ready": True,
                        "interface": "wlan0",
                        "bind_address": "10.55.0.1",
                    },
                    "nodes": [],
                }

            core = FakeCore()
            provider = ServiceStatusProvider(
                core,
                telemetry_database=telemetry,
                alert_database=alerts,
                advisory=FakeAdvisory(),
                command_runner=command_runner,
                service_agent_reader=service_agent_reader,
                tcp_probe=lambda host, port, timeout: True,
            )
            snapshot = provider.get_snapshot()

            self.assertTrue(snapshot["available"])
            self.assertTrue(snapshot["read_only"])
            self.assertEqual(snapshot["system"]["power"]["mask_hex"], "0x50000")
            self.assertFalse(snapshot["system"]["power"]["undervoltage_now"])
            self.assertTrue(snapshot["system"]["power"]["undervoltage_occurred"])
            self.assertEqual(snapshot["core"]["mode"], "STOP")
            self.assertEqual(snapshot["core"]["active_alert_count"], 1)
            self.assertFalse(snapshot["core"]["alert_v2"]["control_policy_applied"])
            self.assertEqual(snapshot["data"]["telemetry"]["samples"], 2)
            self.assertEqual(snapshot["data"]["telemetry"]["pending_sync"], 1)
            self.assertEqual(snapshot["data"]["alerts"]["records"], 2)
            self.assertEqual(snapshot["data"]["alerts"]["active_records"], 1)
            self.assertTrue(snapshot["network"]["ai_server"]["reachable"])
            self.assertTrue(snapshot["network"]["mqtt"]["reachable"])
            self.assertTrue(snapshot["network"]["service_plane"]["available"])
            self.assertEqual(
                core.requests,
                [
                    {"command": "status"},
                    {"command": "alerts", "limit": 1},
                ],
            )
            self.assertTrue(commands)
            self.assertTrue(
                all(
                    command[0]
                    in {
                        "/usr/bin/vcgencmd",
                        "/usr/bin/systemctl",
                        "/usr/sbin/ip",
                        "/usr/bin/ip",
                    }
                    for command in commands
                )
            )

    def test_service_endpoint_is_get_only_and_does_not_proxy_commands(self) -> None:
        core = FakeCore()
        app = AlertHistoryWebApplication(core, service_status=FakeServiceProvider())

        response = app.handle("GET", "/api/v1/service/status")
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["ok"])
        self.assertTrue(response.payload["service"]["read_only"])
        self.assertEqual(core.requests, [])

        denied = app.handle("POST", "/api/v1/service/status", {})
        self.assertEqual(denied.status, 404)
        self.assertEqual(core.requests, [])

    def test_service_gui_is_read_only_and_staged_into_existing_shell(self) -> None:
        js = (STATIC / "service-dashboard.js").read_text(encoding="utf-8")
        css = (STATIC / "service-dashboard.css").read_text(encoding="utf-8")
        server = (ROOT / "src" / "ventilation_core" / "web" / "server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('SERVICE_PATH = "/service"', js)
        self.assertIn('fetch("/api/v1/service/status"', js)
        self.assertIn("READ-ONLY", js)
        self.assertNotIn('method: "POST"', js)
        self.assertNotIn('method: "PUT"', js)
        self.assertNotIn('method: "DELETE"', js)
        self.assertNotIn("/api/v1/manual/", js)
        self.assertNotIn("systemctl", js)
        self.assertNotIn("vcgencmd", js)
        self.assertIn("v2-service-summary", css)
        self.assertIn('"/service", "/service/"', server)
        self.assertIn('"service-dashboard.js"', server)
        self.assertIn('"service-dashboard.css"', server)
        self.assertIn("service_js.read_bytes()", server)
        self.assertIn("service_css.read_bytes()", server)

    def test_web_main_wires_service_provider_without_touching_core_runtime(self) -> None:
        main = (ROOT / "src" / "ventilation_core" / "web" / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("ServiceStatusProvider", main)
        self.assertIn("service_status=service_status", main)
        self.assertIn("WVC_AI_SERVER_HOST", main)
        self.assertIn("WVC_AI_SERVER_PORT", main)

        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "runtime" / "server.py"),
            "7e84987728fba6471bc1220cc3698bc6f8df07db",
        )
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "application" / "alert_registry.py"),
            "097dbd9ad975e6f6c1a8239f56495cf1284bdd41",
        )
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "infrastructure" / "sqlite_alert_store.py"),
            "8a232fe46142186e9564ba53c8b43f5ca6bf14a1",
        )

    def test_ai_telemetry_send_logic_remains_byte_for_byte_unchanged(self) -> None:
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "telemetry" / "agent.py"),
            "54cfbcaa2fa1b5a3442cf7392e69097238d0a096",
        )
        self.assertEqual(
            git_blob_sha(ROOT / "src" / "ventilation_core" / "telemetry" / "http_client.py"),
            "1f43c280117f9ecdff63e539e0d5fec380aee26b",
        )


if __name__ == "__main__":
    unittest.main()
