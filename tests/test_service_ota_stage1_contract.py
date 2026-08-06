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
