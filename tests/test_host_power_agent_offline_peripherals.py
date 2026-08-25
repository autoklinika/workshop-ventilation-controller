from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest

from ventilation_core.host_power_agent import HostPowerAgent
from ventilation_core.web.host_power import HostPowerClient


def _stop_response(*, aero_online: bool, aero_usable: bool, extract_voltage: float = 0.0) -> dict[str, object]:
    return {
        "ok": True,
        "state": {
            "mode": "STOP",
            "setpoints": {
                "supply_voltage": 0.0,
                "extract_voltage": extract_voltage,
            },
            "output_state_known": True,
            "aero_bus": {
                "online": aero_online,
                "usable": aero_usable,
            },
        },
    }


def _aero_success(kind: str) -> dict[str, object]:
    return {
        "ok": True,
        "aero_control": {
            "kind": kind,
            "target_value": 0,
            "state": "succeeded",
            "physical_confirmation": True,
            "observed_power": {
                "fan_1_percent": 0,
                "fan_2_percent": 0,
            },
        },
    }


class HostPowerOfflinePeripheralsTest(unittest.TestCase):
    def _serve_agent(
        self,
        socket_path: Path,
        *,
        launched: list[tuple[str, ...]],
        core_requester,
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

    def test_shutdown_is_allowed_when_aero_is_already_offline_and_local_outputs_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            calls: list[dict[str, object]] = []

            def core_requester(payload: dict[str, object]) -> dict[str, object]:
                calls.append(dict(payload))
                if payload.get("command") == "stop":
                    return _stop_response(aero_online=False, aero_usable=False)
                raise AssertionError(f"offline AERO must not be commanded: {payload!r}")

            stop, thread = self._serve_agent(
                socket_path,
                launched=launched,
                core_requester=core_requester,
            )
            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("shutdown")

            self.assertEqual(response, {"ok": True, "accepted": True, "action": "shutdown"})
            self.assertEqual(calls, [{"command": "stop"}])

            for _ in range(100):
                if launched:
                    break
                time.sleep(0.01)
            self.assertEqual(launched, [("/usr/bin/systemctl", "--no-block", "poweroff")])
            self._stop_agent(stop, thread)

    def test_shutdown_still_rejects_nonzero_local_output_when_aero_is_offline(self) -> None:
        agent = HostPowerAgent(
            Path("/tmp/not-used.sock"),
            core_requester=lambda payload: _stop_response(
                aero_online=False,
                aero_usable=False,
                extract_voltage=1.0,
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "fan outputs are not 0 V"):
            agent._prepare_peripherals_for_poweroff()

    def test_online_aero_confirmation_failure_is_diagnostic_not_shutdown_interlock(self) -> None:
        calls: list[dict[str, object]] = []

        def core_requester(payload: dict[str, object]) -> dict[str, object]:
            calls.append(dict(payload))
            command = payload.get("command")
            if command == "stop":
                return _stop_response(aero_online=True, aero_usable=True)
            if command == "aero-airing":
                return _aero_success("airing")
            if command == "aero-speed":
                return {"ok": False, "error": "AERO speed confirmation failed"}
            raise AssertionError(f"unexpected core request: {payload!r}")

        agent = HostPowerAgent(
            Path("/tmp/not-used.sock"),
            core_requester=core_requester,
        )

        # Local EC STOP/0 V is the shutdown interlock. A peripheral
        # communication/confirmation failure must not block host poweroff.
        agent._prepare_peripherals_for_poweroff()

        self.assertEqual(
            calls,
            [
                {"command": "stop"},
                {"command": "aero-airing", "enabled": False},
                {"command": "aero-speed", "speed": 0},
            ],
        )

    def test_ambiguous_aero_state_attempts_safe_but_does_not_block_shutdown(self) -> None:
        calls: list[dict[str, object]] = []

        def core_requester(payload: dict[str, object]) -> dict[str, object]:
            calls.append(dict(payload))
            if payload.get("command") == "stop":
                response = _stop_response(aero_online=False, aero_usable=False)
                # Ambiguous state: not the explicit offline+unusable shortcut.
                response["state"]["aero_bus"] = {"online": False, "usable": True}
                return response
            return {"ok": False, "error": "AERO unavailable"}

        agent = HostPowerAgent(
            Path("/tmp/not-used.sock"),
            core_requester=core_requester,
        )

        # Best effort means both safe commands are attempted, but their
        # transport failures do not veto shutdown after local EC safety passed.
        agent._prepare_peripherals_for_poweroff()

        self.assertEqual(
            calls,
            [
                {"command": "stop"},
                {"command": "aero-airing", "enabled": False},
                {"command": "aero-speed", "speed": 0},
            ],
        )


if __name__ == "__main__":
    unittest.main()
