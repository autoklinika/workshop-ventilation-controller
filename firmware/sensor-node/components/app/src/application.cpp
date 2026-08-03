#include "app/application.hpp"

#include <cmath>

#include "config/board_config.hpp"
#include "config/firmware_config.hpp"
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
    LOG_INFO(kTag, "Stage 1 runtime started; USB log is the active test interface");

    while (true) {
        sensor_service_.poll();
        log_measurement_if_new();
        update_status_led();

        const bool platform_healthy = diagnostics_.snapshot().gpio_ready && diagnostics_.snapshot().i2c_ready;
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
    return ESP_OK;
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
