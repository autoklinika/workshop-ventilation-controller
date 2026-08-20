from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest

from ventilation_core.host_power_agent import HostPowerAgent
from ventilation_core.web.host_power import HostPowerClient


ROOT = Path(__file__).resolve().parents[1]


class HostPowerAgentTest(unittest.TestCase):
    def test_agent_accepts_restart_over_local_unix_socket_and_launches_fixed_command(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            socket_path = Path(tempdir) / "host-power.sock"
            launched: list[tuple[str, ...]] = []
            stop = threading.Event()
            agent = HostPowerAgent(
                socket_path,
                action_delay_seconds=0.01,
                command_launcher=launched.append,
            )
            thread = threading.Thread(target=agent.serve, args=(stop,), daemon=True)
            thread.start()

            for _ in range(100):
                if socket_path.exists():
                    break
                time.sleep(0.01)
            self.assertTrue(socket_path.exists())

            response = HostPowerClient(socket_path, timeout_seconds=1.0).request("restart")
            self.assertEqual(response, {"ok": True, "accepted": True, "action": "restart"})

            for _ in range(100):
                if launched:
                    break
                time.sleep(0.01)
            self.assertEqual(launched, [("/usr/bin/systemctl", "reboot")])

            stop.set()
            thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())

    def test_protocol_has_only_two_exact_actions_and_no_extra_keys(self) -> None:
        self.assertEqual(
            HostPowerAgent._decode_action(b'{"action":"shutdown"}'),
            "shutdown",
        )
        self.assertEqual(
            HostPowerAgent._decode_action(b'{"action":"restart"}'),
            "restart",
        )
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
        self.assertIn('(\"/usr/bin/systemctl\", \"poweroff\")', source)
        self.assertIn('(\"/usr/bin/systemctl\", \"reboot\")', source)


if __name__ == "__main__":
    unittest.main()
