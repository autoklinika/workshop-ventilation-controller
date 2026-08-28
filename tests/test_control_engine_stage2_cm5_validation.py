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

    def test_harness_seeds_zigbee_roles_exactly_like_production(self) -> None:
        for expected in (
            "SUPPLY_NAME=temp_nawiew",
            "SUPPLY_IEEE=0xa4c13810e66fffff",
            "EXTRACT_NAME=temp_wywiew",
            "EXTRACT_IEEE=0xa4c13810bdedffff",
            "--zigbee-supply-name $SUPPLY_NAME",
            "--zigbee-supply-ieee $SUPPLY_IEEE",
            "--zigbee-extract-name $EXTRACT_NAME",
            "--zigbee-extract-ieee $EXTRACT_IEEE",
            "--zigbee-roles-file $TEST_ROOT/zigbee-roles.json",
        ):
            self.assertIn(expected, self.text)

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

    def test_harness_keeps_outputs_zero_and_forbids_host_power_actions(self) -> None:
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
        ):
            self.assertNotIn(forbidden, self.text)
        self.assertEqual(self.text.count("--enable-scheduled-shutdown"), 1)

    def test_harness_proves_host_rtc_and_boot_are_unchanged(self) -> None:
        for expected in (
            'BOOT_ID_BEFORE="$(cat /proc/sys/kernel/random/boot_id)"',
            'HOST_POWER_PID_BEFORE="$(unit_pid wvc-host-power.service)"',
            'WAKEALARM_BEFORE="$(read_wakealarm)"',
            '[ "$boot_id" = "$BOOT_ID_BEFORE" ]',
            '[ "$host_pid" = "$HOST_POWER_PID_BEFORE" ]',
            '[ "$wakealarm" = "$WAKEALARM_BEFORE" ]',
            '*"12 V domain ON"*',
        ):
            self.assertIn(expected, self.text)
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

    def test_harness_validates_zigbee_freshness_from_actual_timestamp(self) -> None:
        for expected in (
            "ZIGBEE_STALE_SECONDS=14400",
            'source_timestamp = supply.get("last_seen") or supply.get("last_message_at")',
            'expected_age = max(0.0, (evaluated_at - source_dt).total_seconds())',
            'actual_reason != "TEMPERATURE_TIMESTAMP_UNAVAILABLE"',
            'actual_reason != "TEMPERATURE_STALE"',
            'actual_reason != "OK"',
            'actual_usable is not False',
            'actual_stale is not True',
            'actual_usable is not True',
            'actual_stale is not False',
            'if actual_delta is not None:',
            "expected_delta = inside_temp - float(supply[\"temperature_celsius\"])",
        ):
            self.assertIn(expected, self.text)

    def test_harness_does_not_require_zigbee_to_publish_during_test_window(self) -> None:
        self.assertNotIn("Zigbee supply temperature not yet usable", self.text)
        self.assertIn('"zigbee_supply_freshness": freshness', self.text)
        self.assertIn('"zigbee_supply_timestamp": source_timestamp', self.text)

    def test_harness_requires_shadow_only_contract(self) -> None:
        self.assertIn('shadow.get("actuation_supported") is not False', self.text)
        self.assertIn('shadow.get("configuration_persistent") is not True', self.text)
        self.assertIn('zone.get("proposed_supply_voltage") is not None', self.text)
        self.assertIn('zone.get("proposed_extract_voltage") is not None', self.text)
        self.assertIn('zones[2].get("proposed_aero_speed") is not None', self.text)

    def test_failure_path_restores_production_main(self) -> None:
        for expected in (
            "trap emergency_rollback EXIT INT TERM",
            'sudo rm -f "$CORE_DROPIN"',
            'sudo systemctl restart "$CORE_UNIT"',
            'unit_cwd "$MAIN_PID_AFTER")" = "$ROOT"',
            '[ "$(git -C "$ROOT" rev-parse HEAD)" = "$EXPECTED_BASE" ]',
            "ROLLOUT_STARTED=0",
        ):
            self.assertIn(expected, self.text)


if __name__ == "__main__":
    unittest.main()
