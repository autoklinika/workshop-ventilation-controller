#include "app/application.hpp"

#include <cmath>
#include <cstdio>
#include <cstdint>

#include "config/board_config.hpp"
#include "config/firmware_config.hpp"
#include "config/modbus_address.hpp"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "logging/log.hpp"
#include "platform/boot_info.hpp"

namespace app {
namespace {
constexpr char kTag[] = "sensor_node";

float value_or_nan(const sen55::Measurement& measurement,
                   const sen55::MeasurementAvailability field,
                   const float value)
{
    return measurement.available(field) ? value : NAN;
}
}  // namespace

Application::Application()
    : sen55_(i2c_bus_, sen55_i2c_device_), sensor_service_(sen55_, diagnostics_)
{
}

[[noreturn]] void Application::run()
{
    logging::initialize();
    platform::BootInfo::log();

    const esp_err_t result = initialize();
    if (result != ESP_OK) {
        fatal_restart(result, "application_initialize");
    }

    sensor_service_.start();
    start_optional_service_wifi();
    LOG_INFO(kTag,
             "Stage 1 service OTA runtime started; SEN55 and read-only Modbus RTU slave=%u remain production services",
             static_cast<unsigned>(modbus_slave_.slave_address()));

#ifdef CONFIG_WVC_OTA_ROLLBACK_TEST_IMAGE
    const bool rollback_test_pending = ota_health_guard_.confirmation_pending();
    const std::int64_t rollback_test_restart_at_us =
        rollback_test_pending
            ? esp_timer_get_time() +
                  static_cast<std::int64_t>(
                      config::firmware::kOtaRollbackTestRestartDelayMs) *
                      1'000
            : 0;
    if (rollback_test_pending) {
        LOG_WARN(kTag,
                 "ROLLBACK TEST IMAGE active: pending OTA image will restart after %lu ms without confirmation",
                 static_cast<unsigned long>(
                     config::firmware::kOtaRollbackTestRestartDelayMs));
    } else {
        LOG_WARN(kTag,
                 "ROLLBACK TEST IMAGE inactive at runtime because current image is not pending verification");
    }
#endif

    while (true) {
        sensor_service_.poll();

        const esp_err_t modbus_result = modbus_slave_.refresh(
            sensor_service_.latest_measurement(), diagnostics_.snapshot());
        if (modbus_result != ESP_OK) {
            LOG_WARN(kTag,
                     "Modbus register refresh failed: %s",
                     esp_err_to_name(modbus_result));
        }

        publish_service_snapshot();
        log_measurement_if_new();
        update_status_led();

        const diagnostics::Snapshot& snapshot = diagnostics_.snapshot();
        const modbus::Activity modbus_activity = modbus_slave_.activity();
        const std::int64_t now_us = esp_timer_get_time();

#ifdef CONFIG_WVC_OTA_ROLLBACK_TEST_IMAGE
        if (rollback_test_pending && now_us >= rollback_test_restart_at_us) {
            LOG_ERROR(kTag,
                      "ROLLBACK TEST IMAGE forcing restart while OTA confirmation is still pending");
            vTaskDelay(pdMS_TO_TICKS(250));
            esp_restart();
        }
#endif

        const bool measurement_fresh = snapshot.last_success_us > 0 &&
                                       now_us >= snapshot.last_success_us &&
                                       (now_us - snapshot.last_success_us) <=
                                           static_cast<std::int64_t>(
                                               config::firmware::kMeasurementStaleAfterMs) *
                                               1'000;
        const bool platform_healthy = snapshot.gpio_ready &&
                                      snapshot.i2c_ready &&
                                      snapshot.rs485_ready &&
                                      snapshot.sensor_present &&
                                      snapshot.measurement_running &&
                                      snapshot.first_measurement_received &&
                                      snapshot.sensor_state == diagnostics::SensorState::kRunning &&
                                      snapshot.successful_measurements > 0 &&
                                      snapshot.last_error == ESP_OK &&
                                      measurement_fresh &&
                                      modbus_activity.monitor_ready;
        const esp_err_t ota_result = ota_health_guard_.confirm_if_due(platform_healthy);
        if (ota_result != ESP_OK) {
            LOG_WARN(kTag, "OTA image confirmation failed: %s", esp_err_to_name(ota_result));
        }

        vTaskDelay(pdMS_TO_TICKS(config::firmware::kApplicationLoopPeriodMs));
    }
}

esp_err_t Application::initialize()
{
    esp_err_t result = ota_health_guard_.initialize();
    if (result != ESP_OK) {
        LOG_WARN(kTag, "OTA health guard initialization warning: %s", esp_err_to_name(result));
    }

    result = status_led_.initialize();
    if (result != ESP_OK) {
        return result;
    }
    diagnostics_.mark_gpio_ready();

    result = i2c_bus_.initialize();
    if (result != ESP_OK) {
        return result;
    }
    diagnostics_.mark_i2c_ready();

    result = sen55_i2c_device_.initialize(i2c_bus_,
                                          config::board::kSen55Address,
                                          config::board::kI2cFrequencyHz);
    if (result != ESP_OK) {
        return result;
    }

    std::uint8_t modbus_address{};
    result = config::load_modbus_slave_address(modbus_address);
    if (result != ESP_OK) {
        LOG_ERROR(kTag,
                  "Cannot resolve Modbus slave address: %s",
                  esp_err_to_name(result));
        return result;
    }

    LOG_INFO(kTag,
             "resolved Modbus slave address=%u",
             static_cast<unsigned>(modbus_address));

    result = modbus_slave_.initialize(modbus_address);
    if (result != ESP_OK) {
        return result;
    }
    diagnostics_.mark_rs485_ready();

    result = config::load_service_credentials(service_credentials_);
    if (result == ESP_OK) {
        service_credentials_available_ = true;
        LOG_INFO(kTag,
                 "service credentials available for node_id=%s; secrets are not logged",
                 service_credentials_.node_id.data());
    } else if (result == ESP_ERR_NVS_NOT_FOUND || result == ESP_ERR_NOT_FOUND) {
        LOG_INFO(kTag,
                 "service credentials not provisioned; optional Wi-Fi remains disabled");
    } else {
        LOG_WARN(kTag,
                 "service credentials invalid or unavailable: %s; optional Wi-Fi remains disabled",
                 esp_err_to_name(result));
    }
    return ESP_OK;
}

void Application::start_optional_service_wifi()
{
    if (!service_credentials_available_) {
        return;
    }

    esp_err_t network_result = esp_netif_init();
    if (network_result != ESP_OK && network_result != ESP_ERR_INVALID_STATE) {
        LOG_WARN(kTag,
                 "service network initialization failed: %s; SEN55 and Modbus continue",
                 esp_err_to_name(network_result));
        return;
    }
    network_result = esp_event_loop_create_default();
    if (network_result != ESP_OK && network_result != ESP_ERR_INVALID_STATE) {
        LOG_WARN(kTag,
                 "service event loop initialization failed: %s; SEN55 and Modbus continue",
                 esp_err_to_name(network_result));
        return;
    }

    const esp_err_t ota_result = service_ota_.start(service_credentials_);
    if (ota_result != ESP_OK) {
        LOG_WARN(kTag,
                 "manual service OTA endpoint did not start: %s; SEN55 and Modbus continue",
                 esp_err_to_name(ota_result));
    }

    publish_service_snapshot();
    const esp_err_t wifi_result = service_wifi_.start(service_credentials_);
    if (wifi_result != ESP_OK) {
        LOG_WARN(kTag,
                 "optional service Wi-Fi did not start: %s; SEN55 and Modbus continue",
                 esp_err_to_name(wifi_result));
    }
}

void Application::publish_service_snapshot()
{
    if (!service_credentials_available_) {
        return;
    }

    const diagnostics::Snapshot& diagnostic_snapshot = diagnostics_.snapshot();
    const modbus::Activity modbus = modbus_slave_.activity();
    service_wifi::HeartbeatSnapshot snapshot{};
    std::snprintf(snapshot.sensor_state.data(),
                  snapshot.sensor_state.size(),
                  "%s",
                  diagnostics::to_string(diagnostic_snapshot.sensor_state));
    snapshot.last_measurement_success_us = diagnostic_snapshot.last_success_us;
    snapshot.sensor_last_error = diagnostic_snapshot.last_error;
    snapshot.sensor_detection_failures = diagnostic_snapshot.detection_failures;
    snapshot.sensor_communication_failures = diagnostic_snapshot.communication_failures;
    snapshot.sensor_crc_failures = diagnostic_snapshot.crc_failures;
    snapshot.sensor_successful_measurements = diagnostic_snapshot.successful_measurements;
    snapshot.rs485_ready = diagnostic_snapshot.rs485_ready;
    snapshot.modbus_slave = modbus_slave_.slave_address();
    snapshot.modbus_monitor_ready = modbus.monitor_ready;
    snapshot.modbus_requests_total = modbus.request_count;
    snapshot.last_modbus_request_us = modbus.last_request_us;
    snapshot.modbus_service_errors = modbus.service_error_count;
    service_wifi_.update_snapshot(snapshot);
}

void Application::update_status_led()
{
    if (sensor_service_.online()) {
        if (!led_state_) {
            led_state_ = true;
            static_cast<void>(status_led_.set(true));
        }
        return;
    }

    const std::int64_t now_us = esp_timer_get_time();
    if ((now_us - last_led_toggle_us_) >= 500'000) {
        last_led_toggle_us_ = now_us;
        led_state_ = !led_state_;
        static_cast<void>(status_led_.set(led_state_));
    }
}

void Application::log_measurement_if_new()
{
    if (!sensor_service_.has_new_measurement(last_logged_sequence_)) {
        return;
    }

    const sen55::Measurement& value = sensor_service_.latest_measurement();
    last_logged_sequence_ = value.sequence;

    LOG_INFO(kTag,
             "measurement=%llu PM1.0=%.1f PM2.5=%.1f PM4.0=%.1f PM10=%.1f RH=%.2f T=%.2f VOC=%.1f NOx=%.1f mask=0x%02X",
             static_cast<unsigned long long>(value.sequence),
             value_or_nan(value, sen55::kPm1Available, value.pm1_0),
             value_or_nan(value, sen55::kPm2_5Available, value.pm2_5),
             value_or_nan(value, sen55::kPm4Available, value.pm4_0),
             value_or_nan(value, sen55::kPm10Available, value.pm10_0),
             value_or_nan(value, sen55::kHumidityAvailable, value.humidity_percent),
             value_or_nan(value, sen55::kTemperatureAvailable, value.temperature_celsius),
             value_or_nan(value, sen55::kVocAvailable, value.voc_index),
             value_or_nan(value, sen55::kNoxAvailable, value.nox_index),
             value.availability_mask);
}

void Application::fatal_restart(const esp_err_t error, const char* operation)
{
    LOG_ERROR(kTag, "%s failed: %s; restarting", operation, esp_err_to_name(error));
    static_cast<void>(status_led_.set(false));
    vTaskDelay(pdMS_TO_TICKS(2'000));
    esp_restart();
    while (true) {
        vTaskDelay(portMAX_DELAY);
    }
}

}  // namespace app
