from __future__ import annotations

from pathlib import Path
import unittest

from ventilation_core.rtc_wake_agent import RtcWakeAgent


class RtcWakeAgentM6Test(unittest.TestCase):
    def test_protocol_accepts_only_narrow_commands(self) -> None:
        self.assertEqual(RtcWakeAgent._decode(b'{"command":"read"}'), {"command": "read"})
        self.assertEqual(RtcWakeAgent._decode(b'{"command":"clear"}'), {"command": "clear"})
        arm = RtcWakeAgent._decode(
            b'{"command":"arm","wake_epoch":1787838037,"minimum_lead_seconds":120}'
        )
        self.assertEqual(arm["wake_epoch"], 1787838037)
        for raw in (
            b'{"command":"shutdown"}',
            b'{"command":"arm","wake_epoch":1787838037,"minimum_lead_seconds":120,"x":1}',
            b'{"command":"read","x":1}',
            b'{"command":"arm","wake_epoch":true,"minimum_lead_seconds":120}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    RtcWakeAgent._decode(raw)

    def test_agent_source_has_no_host_power_or_shell_execution(self) -> None:
        source = Path("src/ventilation_core/rtc_wake_agent.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("poweroff", source)
        self.assertNotIn("reboot", source)
        self.assertNotIn("host_power", source)

    def test_systemd_agent_is_local_privileged_and_core_remains_unprivileged(self) -> None:
        rtc_unit = Path("deploy/systemd/wvc-rtc-wake.service").read_text(encoding="utf-8")
        core_unit = Path("deploy/systemd/ventilation-core.service").read_text(encoding="utf-8")
        self.assertIn("User=root", rtc_unit)
        self.assertIn("Group=wentylacja", rtc_unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", rtc_unit)
        self.assertIn("User=wentylacja", core_unit)
        self.assertIn("NoNewPrivileges=true", core_unit)
        self.assertIn("Wants=wvc-rtc-wake.service", core_unit)
        self.assertNotIn("--enable-scheduled-shutdown", core_unit)


if __name__ == "__main__":
    unittest.main()
