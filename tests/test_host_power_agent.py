from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest

from ventilation_core.host_power_agent import HostPowerAgent
from ventilation_core.web.host_power import HostPowerClient


ROOT = Path(__file__).resolve().parents[1]


def _ready_stop_response() -> dict[str, object]:
    return {
        "ok": True,
        "state": {
            "mode": "STOP",
            "setpoints": {"supply_voltage": 0.0, "extract_voltage": 0.0},
            "output_state_known": True,
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


class HostPowerAgentTest(unittest.TestCase):
    def _serve_agent(
        self,
        socket_path: Path,
        *,
        launched: list[tuple[str, ...]],
        core_requester=None,
    ) -> tuple[threading.Event, threading.Thread]:
        stop = threading.Event()
        agent = HostPowerAgent(
            socket_path,
            action_delay_seconds=0.01,
            command_launcher=launched.append,
            core_requester=core_requester,
        )
        thread = threading.Thread(target=agent.serve, args=(stop,), daemon=True)
        thread.start()
        for _ in range(100):
            if socket_path.exists():
                break
            time.sleep(0.01)
        self.assertTrue(socket_path.exists())
        return stop, thread

    @staticmethod
    def _stop_agent(stop: threading.Event, thread: threading.Thread) -> None:
        stop.set()
        thread.join(timeout=2.0)

    def test_agent_accepts_restart_over_local_unix_socket_and_launches_fixed_command(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            core_calls: list[dict[str, object]] = []

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                core_calls.append(dict(payload))
                raise AssertionError("restart must not touch ventilation peripherals")

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("restart")
            self.assertEqual(response, {"ok": True, "accepted": True, "action": "restart"})

            for _ in range(100):
                if launched:
                    break
                time.sleep(0.01)
            self.assertEqual(launched, [("/usr/bin/systemctl", "--no-block", "reboot")])
            self.assertEqual(core_calls, [])
            self._stop_agent(stop, thread)
            self.assertFalse(thread.is_alive())

    def test_shutdown_confirms_fans_airing_and_aero_zero_before_poweroff(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            calls: list[dict[str, object]] = []

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                calls.append(dict(payload))
                command = payload.get("command")
                if command == "stop":
                    return _ready_stop_response()
                if command == "aero-airing":
                    self.assertIs(payload.get("enabled"), False)
                    return _aero_success("airing")
                if command == "aero-speed":
                    self.assertEqual(payload.get("speed"), 0)
                    return _aero_success("speed")
                raise AssertionError(f"unexpected core request: {payload!r}")

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("shutdown")
            self.assertEqual(response, {"ok": True, "accepted": True, "action": "shutdown"})
            self.assertEqual(
                calls,
                [
                    {"command": "stop"},
                    {"command": "aero-airing", "enabled": False},
                    {"command": "aero-speed", "speed": 0},
                ],
            )

            for _ in range(100):
                if launched:
                    break
                time.sleep(0.01)
            self.assertEqual(launched, [("/usr/bin/systemctl", "--no-block", "poweroff")])
            self._stop_agent(stop, thread)

    def test_shutdown_is_rejected_and_poweroff_not_launched_when_aero_zero_is_not_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            calls: list[dict[str, object]] = []

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                calls.append(dict(payload))
                if payload.get("command") == "stop":
                    return _ready_stop_response()
                if payload.get("command") == "aero-airing":
                    return _aero_success("airing")
                return {"ok": False, "error": "AERO BUS unavailable"}

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("shutdown")
            self.assertFalse(response["ok"])
            self.assertIn("peripheral shutdown not confirmed", str(response["error"]))
            time.sleep(0.05)
            self.assertEqual(launched, [])
            self.assertEqual(calls[-1], {"command": "aero-speed", "speed": 0})
            self._stop_agent(stop, thread)

    def test_shutdown_rejects_speed_zero_when_physical_aero_fans_are_not_zero(self) -> None:
        launched: list[tuple[str, ...]] = []
        calls: list[dict[str, object]] = []

        def core_requester(payload: dict[str, object]) -> dict[str, object]:
            calls.append(dict(payload))
            command = payload.get("command")
            if command == "stop":
                return _ready_stop_response()
            if command == "aero-airing":
                return _aero_success("airing", fan_power=60)
            if command == "aero-speed":
                return _aero_success("speed", fan_power=60)
            raise AssertionError(f"unexpected core request: {payload!r}")

        agent = HostPowerAgent(
            Path("/tmp/not-used.sock"),
            command_launcher=launched.append,
            core_requester=core_requester,
        )
        with self.assertRaisesRegex(RuntimeError, "AERO fan power is not 0%"):
            agent._prepare_peripherals_for_poweroff()
        self.assertEqual(launched, [])
        self.assertEqual(calls[-1], {"command": "aero-speed", "speed": 0})

    def test_shutdown_rejects_aero_result_without_physical_confirmation(self) -> None:
        launched: list[tuple[str, ...]] = []

        def core_requester(payload: dict[str, object]) -> dict[str, object]:
            command = payload.get("command")
            if command == "stop":
                return _ready_stop_response()
            response = _aero_success("airing" if command == "aero-airing" else "speed")
            if command == "aero-speed":
                response["aero_control"]["physical_confirmation"] = False
            return response

        agent = HostPowerAgent(
            Path("/tmp/not-used.sock"),
            command_launcher=launched.append,
            core_requester=core_requester,
        )
        with self.assertRaisesRegex(RuntimeError, "lacks physical confirmation"):
            agent._prepare_peripherals_for_poweroff()
        self.assertEqual(launched, [])

    def test_shutdown_rejects_unconfirmed_zero_volt_fan_state(self) -> None:
        launched: list[tuple[str, ...]] = []
        agent = HostPowerAgent(
            Path("/tmp/not-used.sock"),
            command_launcher=launched.append,
            core_requester=lambda _payload: {
                "ok": True,
                "state": {
                    "mode": "STOP",
                    "setpoints": {"supply_voltage": 0.0, "extract_voltage": 1.0},
                    "output_state_known": True,
                },
            },
        )
        with self.assertRaisesRegex(RuntimeError, "fan outputs are not 0 V"):
            agent._prepare_peripherals_for_poweroff()
        self.assertEqual(launched, [])

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

    def test_agent_source_never_uses_shell_true_or_browser_command_text(self) -> None:
        source = (ROOT / "src" / "ventilation_core" / "host_power_agent.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("eval(", source)
        self.assertIn('(\"/usr/bin/systemctl\", \"--no-block\", \"poweroff\")', source)
        self.assertIn('(\"/usr/bin/systemctl\", \"--no-block\", \"reboot\")', source)
        self.assertIn('{"command": "stop"}', source)
        self.assertIn('{"command": "aero-airing", "enabled": False}', source)
        self.assertIn('{"command": "aero-speed", "speed": 0}', source)
        self.assertIn("physical_confirmation", source)
        self.assertIn("fan_1_percent", source)
        self.assertIn("fan_2_percent", source)


if __name__ == "__main__":
    unittest.main()
