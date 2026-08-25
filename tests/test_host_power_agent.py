from __future__ import annotations

from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from ventilation_core.host_power_agent import HostPowerAgent
from ventilation_core.web.host_power import HostPowerClient


ROOT = Path(__file__).resolve().parents[1]


def _ready_stop_response(*, aero_unavailable: bool = False) -> dict[str, object]:
    state: dict[str, object] = {
        "mode": "STOP",
        "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
        "output_state_known": True,
    }
    if aero_unavailable:
        state["aero_bus"] = {"online": False, "usable": False}
    return {"ok": True, "state": state}


def _fault_state(*, supply: float = 0.0, extract: float = 0.0) -> dict[str, object]:
    return {
        "ok": True,
        "state": {
            "mode": "FAULT",
            "setpoints": {"supply_voltage": supply, "extract_voltage": extract},
            "output_state_known": False,
            "hardware_ready": False,
            "aero_bus": {"online": False, "usable": False},
        },
    }


def _aero_success(kind: str, *, fan_power: int = 0) -> dict[str, object]:
    return {
        "ok": True,
        "aero_control": {
            "kind": kind,
            "target_value": 0,
            "state": "succeeded",
            "physical_confirmation": True,
            "observed_power": {
                "fan_1_percent": fan_power,
                "fan_2_percent": fan_power,
            },
        },
    }


class _FakePowerDomain:
    def __init__(self, events: list[object], *, fail_off: bool = False) -> None:
        self.events = events
        self.fail_off = fail_off

    def start(self) -> None:
        self.events.append("12v-on")

    def power_off(self) -> None:
        self.events.append("12v-off")
        if self.fail_off:
            raise RuntimeError("relay write failed")

    def close(self) -> None:
        self.events.append("power-domain-close")


class HostPowerAgentTest(unittest.TestCase):
    def _serve_agent(
        self,
        socket_path: Path,
        *,
        launched: list[tuple[str, ...]],
        core_requester,
        power_domain: _FakePowerDomain,
    ) -> tuple[threading.Event, threading.Thread]:
        stop = threading.Event()
        agent = HostPowerAgent(
            socket_path,
            action_delay_seconds=0.01,
            command_launcher=launched.append,
            core_requester=core_requester,
            power_domain=power_domain,
            ready_notifier=lambda _status: None,
        )
        thread = threading.Thread(target=agent.serve, args=(stop,), daemon=True)
        thread.start()

        listening = False
        for _ in range(100):
            if not socket_path.exists():
                time.sleep(0.01)
                continue
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(0.2)
                    client.connect(str(socket_path))
                    client.sendall(b'{"action":"probe"}\n')
                    response = client.recv(4096)
                if b"action must be shutdown or restart" in response:
                    listening = True
                    break
            except OSError:
                pass
            time.sleep(0.01)

        self.assertTrue(listening, "host-power test socket did not become ready")
        return stop, thread

    @staticmethod
    def _stop_agent(stop: threading.Event, thread: threading.Thread) -> None:
        stop.set()
        thread.join(timeout=2.0)

    @staticmethod
    def _wait_for_launch(launched: list[tuple[str, ...]]) -> None:
        for _ in range(100):
            if launched:
                return
            time.sleep(0.01)

    def test_shutdown_orders_local_safe_peripheral_safe_12v_off_then_poweroff(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            events: list[object] = []
            power_domain = _FakePowerDomain(events)

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                command = payload.get("command")
                events.append(command)
                if command == "stop":
                    return _ready_stop_response()
                if command == "aero-airing":
                    return _aero_success("airing")
                if command == "aero-speed":
                    return _aero_success("speed")
                raise AssertionError(payload)

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
                power_domain=power_domain,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("shutdown")
            self.assertEqual(response, {"ok": True, "accepted": True, "action": "shutdown"})
            self._wait_for_launch(launched)

            self.assertEqual(
                events[:5],
                ["12v-on", "stop", "aero-airing", "aero-speed", "12v-off"],
            )
            self.assertEqual(launched, [("/usr/bin/systemctl", "--no-block", "poweroff")])
            self._stop_agent(stop, thread)

    def test_restart_uses_same_safe_sequence_and_12v_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            events: list[object] = []
            power_domain = _FakePowerDomain(events)

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                command = payload.get("command")
                events.append(command)
                if command == "stop":
                    return _ready_stop_response(aero_unavailable=True)
                raise AssertionError("offline AERO must not be commanded")

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
                power_domain=power_domain,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("restart")
            self.assertEqual(response, {"ok": True, "accepted": True, "action": "restart"})
            self._wait_for_launch(launched)

            self.assertEqual(events[:3], ["12v-on", "stop", "12v-off"])
            self.assertEqual(launched, [("/usr/bin/systemctl", "--no-block", "reboot")])
            self._stop_agent(stop, thread)

    def test_aero_communication_failure_does_not_block_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            events: list[object] = []
            power_domain = _FakePowerDomain(events)

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                command = payload.get("command")
                events.append(command)
                if command == "stop":
                    return _ready_stop_response()
                raise TimeoutError("AERO timeout")

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
                power_domain=power_domain,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("shutdown")
            self.assertTrue(response["ok"])
            self._wait_for_launch(launched)

            self.assertEqual(
                events[:5],
                ["12v-on", "stop", "aero-airing", "aero-speed", "12v-off"],
            )
            self.assertEqual(launched, [("/usr/bin/systemctl", "--no-block", "poweroff")])
            self._stop_agent(stop, thread)

    def test_dac_stop_failure_does_not_block_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            events: list[object] = []
            power_domain = _FakePowerDomain(events)

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                command = payload.get("command")
                events.append(command)
                if command == "stop":
                    return {
                        "ok": False,
                        "error": "No response from GP8403 at 0x58: Remote I/O error",
                    }
                if command == "status":
                    return _fault_state()
                raise AssertionError("offline AERO must not be commanded")

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
                power_domain=power_domain,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("shutdown")
            self.assertEqual(response, {"ok": True, "accepted": True, "action": "shutdown"})
            self._wait_for_launch(launched)

            self.assertEqual(events[:4], ["12v-on", "stop", "status", "12v-off"])
            self.assertEqual(launched, [("/usr/bin/systemctl", "--no-block", "poweroff")])
            self._stop_agent(stop, thread)

    def test_unconfirmed_or_nonzero_local_output_does_not_make_shutdown_impossible(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            events: list[object] = []
            power_domain = _FakePowerDomain(events)

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                command = payload.get("command")
                events.append(command)
                if command == "stop":
                    return {
                        "ok": True,
                        "state": {
                            "mode": "STOP",
                            "setpoints": {"supply_voltage": 0.0, "extract_voltage": 1.0},
                            "output_state_known": True,
                        },
                    }
                if command == "status":
                    return _fault_state(extract=1.0)
                raise AssertionError("offline AERO must not be commanded")

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
                power_domain=power_domain,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("shutdown")
            self.assertTrue(response["ok"])
            self._wait_for_launch(launched)

            self.assertEqual(events[:4], ["12v-on", "stop", "status", "12v-off"])
            self.assertEqual(launched, [("/usr/bin/systemctl", "--no-block", "poweroff")])
            self._stop_agent(stop, thread)

    def test_failure_to_command_12v_off_blocks_normal_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            events: list[object] = []
            power_domain = _FakePowerDomain(events, fail_off=True)

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                command = payload.get("command")
                if command == "stop":
                    return _ready_stop_response(aero_unavailable=True)
                raise AssertionError(payload)

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
                power_domain=power_domain,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("shutdown")
            self.assertFalse(response["ok"])
            self.assertIn("relay write failed", str(response["error"]))
            time.sleep(0.05)
            self.assertEqual(launched, [])
            self.assertIn("12v-off", events)
            self._stop_agent(stop, thread)

    def test_protocol_has_only_two_exact_actions_and_no_extra_keys(self) -> None:
        self.assertEqual(HostPowerAgent._decode_action(b'{"action":"shutdown"}'), "shutdown")
        self.assertEqual(HostPowerAgent._decode_action(b'{"action":"restart"}'), "restart")
        for raw in (
            b'{}',
            b'{"action":"halt"}',
            b'{"command":"reboot"}',
            b'{"action":"restart","command":"whoami"}',
            b'[]',
            b'not-json',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    HostPowerAgent._decode_action(raw)

    def test_agent_source_keeps_fixed_commands_and_no_shell_forwarding(self) -> None:
        source = (ROOT / "src" / "ventilation_core" / "host_power_agent.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("eval(", source)
        self.assertIn('("/usr/bin/systemctl", "--no-block", "poweroff")', source)
        self.assertIn('("/usr/bin/systemctl", "--no-block", "reboot")', source)
        self.assertIn('{"command": "stop"}', source)
        self.assertIn('{"command": "status"}', source)
        self.assertIn('{"command": "aero-airing", "enabled": False}', source)
        self.assertIn('{"command": "aero-speed", "speed": 0}', source)
        self.assertIn("must not make the system impossible to power off", source)
        self.assertIn("communication must not block 12 V isolation", source)


if __name__ == "__main__":
    unittest.main()
