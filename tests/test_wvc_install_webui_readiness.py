"""Regression of the bounded WebGUI readiness gate in the root installer.

Only the isolated readiness snippet is executed with mock commands, never
installer actions, systemd writes, RTC, fan controls or a real WebGUI restart.
"""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "tools/install_wvc_event_schedule.sh"


class WebGuiPostRestartGateTests(unittest.TestCase):
    @staticmethod
    def snippet() -> str:
        source = INSTALLER.read_text(encoding="utf-8")
        first = "WEB_READY=0\n"
        last = 'if [[ "$WEB_READY" != 1 ]]; then\n'
        assert source.count(first) == 1 and source.count(last) == 1
        segment = source.split(first, 1)[1].split(last, 1)[0]
        assert 'curl -fsS --connect-timeout 1 --max-time 2' in segment
        assert 'for attempt in $(seq 1 45); do' in segment
        return first + segment.replace("  sleep 1", "  :") + 'test "$WEB_READY" = 1\n'

    @staticmethod
    def mock_command(directory: Path, name: str, source: str) -> None:
        path = directory / name
        path.write_text("#!/bin/sh\n" + source, encoding="utf-8")
        path.chmod(0o700)

    def test_webgui_becomes_ready_on_third_try(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            count = directory / "count"
            self.mock_command(directory, "systemctl", "exit 0\n")
            self.mock_command(
                directory, "curl",
                'number=$(cat "$FAKE_COUNT_FILE" 2>/dev/null || echo 0)\n'
                'number=$((number + 1))\n'
                'echo "$number" > "$FAKE_COUNT_FILE"\n'
                '[ "$number" -ge 3 ]\n',
            )
            env = {**os.environ, "PATH": str(directory) + ":/usr/bin:/bin",
                   "FAKE_COUNT_FILE": str(count)}
            result = subprocess.run(["/bin/bash", "-c", self.snippet()],
                                    text=True, capture_output=True, env=env,
                                    timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WVC_WEBGUI_POST_RESTART_READY_PASS attempt=3", result.stdout)
            self.assertEqual(count.read_text().strip(), "3")

    def test_unavailable_webgui_fails_after_bounded_retries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            count = directory / "count"
            self.mock_command(directory, "systemctl", "exit 0\n")
            self.mock_command(
                directory, "curl",
                'number=$(cat "$FAKE_COUNT_FILE" 2>/dev/null || echo 0)\n'
                'echo $((number + 1)) > "$FAKE_COUNT_FILE"\n'
                'exit 7\n',
            )
            env = {**os.environ, "PATH": str(directory) + ":/usr/bin:/bin",
                   "FAKE_COUNT_FILE": str(count)}
            result = subprocess.run(["/bin/bash", "-c", self.snippet()],
                                    text=True, capture_output=True, env=env,
                                    timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(count.read_text().strip(), "45")

    def test_no_scheduled_poweroff_side_effects_in_readiness_gate(self) -> None:
        segment = self.snippet()
        for forbidden in (
            "systemctl restart", "systemctl poweroff", "systemctl disable",
            "auto-resume", "wvc-autostart-gate.py tick", "RTC_ALARM.write",
        ):
            self.assertNotIn(forbidden, segment)


if __name__ == "__main__":
    unittest.main()
