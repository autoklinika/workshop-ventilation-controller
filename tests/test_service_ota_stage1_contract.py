from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ServiceOtaStage1ContractTests(unittest.TestCase):
    def test_partition_table_and_rollback_are_enabled(self) -> None:
        partitions = (ROOT / "firmware/sensor-node/partitions.csv").read_text(
            encoding="utf-8"
        )
        sdkconfig = (ROOT / "firmware/sensor-node/sdkconfig.defaults").read_text(
            encoding="utf-8"
        )

        self.assertIn("otadata", partitions)
        self.assertIn("ota_0", partitions)
        self.assertIn("ota_1", partitions)
        self.assertIn("CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y", sdkconfig)

    def test_ota_bootstrap_has_stack_corruption_guards(self) -> None:
        sdkconfig = (ROOT / "firmware/sensor-node/sdkconfig.defaults").read_text(
            encoding="utf-8"
        )
        required = (
            "CONFIG_ESP_COREDUMP_STACK_SIZE=2048",
            "CONFIG_FREERTOS_CHECK_STACKOVERFLOW_CANARY=y",
            "CONFIG_FREERTOS_WATCHPOINT_END_OF_STACK=y",
            "CONFIG_COMPILER_STACK_CHECK_MODE_STRONG=y",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, sdkconfig)

    def test_health_guard_requires_continuous_healthy_window(self) -> None:
        header = (
            ROOT
            / "firmware/sensor-node/components/platform/include/platform/ota_health_guard.hpp"
        ).read_text(encoding="utf-8")
        source = (
            ROOT
            / "firmware/sensor-node/components/platform/src/ota_health_guard.cpp"
        ).read_text(encoding="utf-8")

        self.assertIn("healthy_since_us_", header)
        self.assertIn("if (!platform_healthy)", source)
        self.assertIn("healthy_since_us_ = 0", source)
        self.assertIn("continuous health confirmation window started", source)
        self.assertIn("esp_ota_mark_app_valid_cancel_rollback", source)
        self.assertNotIn("started_us_", header)

    def test_application_health_requires_sensor_measurement_and_modbus(self) -> None:
        application = (
            ROOT / "firmware/sensor-node/components/app/src/application.cpp"
        ).read_text(encoding="utf-8")

        required_fragments = (
            "snapshot.sensor_present",
            "snapshot.measurement_running",
            "snapshot.first_measurement_received",
            "diagnostics::SensorState::kRunning",
            "snapshot.successful_measurements > 0",
            "snapshot.last_error == ESP_OK",
            "measurement_fresh",
            "modbus_activity.monitor_ready",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, application)

    def test_rollback_test_image_is_disabled_by_default_and_pending_only(self) -> None:
        kconfig = (
            ROOT / "firmware/sensor-node/components/app/Kconfig.projbuild"
        ).read_text(encoding="utf-8")
        overlay = (
            ROOT / "firmware/sensor-node/sdkconfig.rollback-test.defaults"
        ).read_text(encoding="utf-8")
        application = (
            ROOT / "firmware/sensor-node/components/app/src/application.cpp"
        ).read_text(encoding="utf-8")
        firmware_config = (
            ROOT
            / "firmware/sensor-node/components/config/include/config/firmware_config.hpp"
        ).read_text(encoding="utf-8")

        self.assertIn("config WVC_OTA_ROLLBACK_TEST_IMAGE", kconfig)
        self.assertIn("default n", kconfig)
        self.assertIn("CONFIG_WVC_OTA_ROLLBACK_TEST_IMAGE=y", overlay)
        self.assertIn("ota_health_guard_.confirmation_pending()", application)
        self.assertIn("rollback_test_pending &&", application)
        self.assertIn("esp_restart();", application)
        self.assertIn("kOtaRollbackTestRestartDelayMs = 15'000", firmware_config)
        self.assertIn("0.5.2-stage1-rollback-test", firmware_config)
        self.assertIn("0.5.1-stage1-fix1", firmware_config)

    def test_start_report_keeps_wifi_non_production_and_ota_manual(self) -> None:
        report = (
            ROOT / "docs/reports/KAMOD_SERVICE_OTA_STAGE1_START_PL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("heartbeat Wi-Fi: best effort", report)
        self.assertIn("RS-485 Modbus RTU: jedyny kanał krytyczny", report)
        self.assertIn("GET  /v1/ota/challenge", report)
        self.assertIn("POST /v1/ota/image", report)
        self.assertIn("WVC-OTA1", report)
        self.assertIn("esp_ota_abort", report)
        self.assertIn("Automatyczne OTA na podstawie błędu RS-485 jest zabronione", report)


if __name__ == "__main__":
    unittest.main()
