from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "install_validate_control_engine_stage2_inputs_cm5.sh"


class ControlEngineStage2Cm5ValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HARNESS.read_text(encoding="utf-8")

    def test_harness_has_valid_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(HARNESS)], check=True)

    def test_harness_pins_production_main_and_exact_branch_sha(self) -> None:
        self.assertIn(
            "EXPECTED_BASE=7628c407cfc9c0ea72d262566759ea2d4598fec8",
            self.text,
        )
        self.assertIn(
            'EXPECTED_BRANCH_SHA="${CONTROL_ENGINE_STAGE2_EXPECTED_BRANCH_SHA:-}"',
            self.text,
        )
        self.assertIn('git fetch origin main "$BRANCH"', self.text)
        self.assertIn('[ "$BRANCH_SHA" = "$EXPECTED_BRANCH_SHA" ]', self.text)
        self.assertIn('git worktree add --detach "$WT" "$BRANCH_SHA"', self.text)

    def test_harness_requires_real_connected_peripherals_before_rollout(self) -> None:
        self.assertIn("require_production_peripherals_ready", self.text)
        for expected in (
            'state.get("hardware_ready") is not True',
            'sensor_bus.get("ready") is not True',
            'node.get("online") is True',
            'node.get("usable") is True',
            'node.get("measurement_valid") is True',
            'node.get("measurement_stale") is False',
            'aero.get("online") is True',
            'aero.get("usable") is True',
            'zigbee.get("connected") is True',
            'zigbee.get("bridge_online") is True',
            'for role in ("supply", "extract")',
        ):
            self.assertIn(expected, self.text)

    def test_harness_keeps_local_outputs_zero_and_forbids_host_power_actions(self) -> None:
        self.assertIn('sp.get("supply_voltage") != 0.0', self.text)
        self.assertIn('sp.get("extract_voltage") != 0.0', self.text)
        self.assertIn('float(row.get("rpm") or 0.0) != 0.0', self.text)
        self.assertGreaterEqual(self.text.count("require_zero_output_guard"), 4)
        for forbidden in (
            "systemctl --no-block poweroff",
            "systemctl --no-block reboot",
            "/usr/bin/systemctl poweroff",
            "/usr/bin/systemctl reboot",
            'ctl "$WT/src" shutdown',
            "--enable-scheduled-shutdown",
        ):
            if forbidden == "--enable-scheduled-shutdown":
                # The token is allowed only in the static guard that rejects it.
                self.assertEqual(self.text.count(forbidden), 1)
            else:
                self.assertNotIn(forbidden, self.text)

    def test_harness_proves_host_rtc_and_boot_are_unchanged(self) -> None:
        self.assertIn('BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"', self.text)
        self.assertIn('HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"', self.text)
        self.assertIn('WAKEALARM_BEFORE="$(read_wakealarm)"', self.text)
        self.assertIn('[ "$boot_id" = "$BOOT_ID_BEFORE" ]', self.text)
        self.assertIn('[ "$host_pid" = "$HOST_POWER_PID_BEFORE" ]', self.text)
        self.assertIn('[ "$wakealarm" = "$WAKEALARM_BEFORE" ]', self.text)
        self.assertIn('*"12 V domain ON"*', self.text)
        self.assertGreaterEqual(self.text.count("assert_host_not_touched"), 4)

    def test_harness_compares_sen55_provenance_one_to_one(self) -> None:
        for expected in (
            '"sensor_pm2_5_ug_m3": "pm2_5_ug_m3"',
            '"sensor_pm10_0_ug_m3": "pm10_0_ug_m3"',
            '"sensor_voc_index": "voc_index"',
            '"sensor_nox_index": "nox_index"',
            '"sensor_temperature_celsius": "temperature_celsius"',
            'zone.get("sensor_age_seconds") != node.get("age_seconds")',
            'zone.get("sensor_last_success_at") != node.get("last_success_at")',
            'zone.get("inside_temperature_celsius") != reading.get("temperature_celsius")',
        ):
            self.assertIn(expected, self.text)

    def test_harness_verifies_zigbee_supply_and_temperature_delta(self) -> None:
        self.assertIn('zone1.get("outside_temperature_usable") is not True', self.text)
        self.assertIn('zone1.get("outside_temperature_stale") is not False', self.text)
        self.assertIn('zone1.get("outside_temperature_reason") != "OK"', self.text)
        self.assertIn('zone1.get("outside_temperature_celsius") != supply.get("temperature_celsius")', self.text)
        self.assertIn("expected_delta = inside_temp - supply_temp", self.text)
        self.assertIn("abs(float(actual_delta) - expected_delta) > 1e-6", self.text)

    def test_harness_requires_shadow_only_contract(self) -> None:
        self.assertIn('shadow.get("actuation_supported") is not False', self.text)
        self.assertIn('shadow.get("configuration_persistent") is not True', self.text)
        self.assertIn('zone.get("proposed_supply_voltage") is not None', self.text)
        self.assertIn('zone.get("proposed_extract_voltage") is not None', self.text)
        self.assertIn('zones[2].get("proposed_aero_speed") is not None', self.text)

    def test_failure_path_restores_production_main(self) -> None:
        self.assertIn("trap emergency_rollback EXIT INT TERM", self.text)
        self.assertIn('sudo rm -f "$CORE_DROPIN"', self.text)
        self.assertIn('sudo systemctl restart "$CORE_UNIT"', self.text)
        self.assertIn('unit_cwd "$MAIN_PID_AFTER")" = "$ROOT"', self.text)
        self.assertIn('[ "$(git -C "$ROOT" rev-parse HEAD)" = "$EXPECTED_BASE" ]', self.text)
        self.assertIn("ROLLOUT_STARTED=0", self.text)


if __name__ == "__main__":
    unittest.main()
