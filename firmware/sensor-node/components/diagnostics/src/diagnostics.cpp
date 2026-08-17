#include "diagnostics/diagnostics.hpp"

#include "esp_timer.h"
#include "logging/log.hpp"

namespace diagnostics {
namespace {
constexpr char kTag[] = "diagnostics";
}

void Diagnostics::mark_gpio_ready()
{
    snapshot_.gpio_ready = true;
}

void Diagnostics::mark_i2c_ready()
{
    snapshot_.i2c_ready = true;
}

void Diagnostics::mark_rs485_ready()
{
    snapshot_.rs485_ready = true;
}

void Diagnostics::set_sensor_state(const SensorState state)
{
    if (snapshot_.sensor_state != state) {
        snapshot_.sensor_state = state;
        LOG_INFO(kTag, "sensor_state=%s", to_string(state));
    }
}

void Diagnostics::mark_sensor_detected()
{
    snapshot_.sensor_present = true;
    snapshot_.last_error = ESP_OK;
}

void Diagnostics::mark_sensor_offline(const esp_err_t error)
{
    snapshot_.sensor_present = false;
    snapshot_.measurement_running = false;
    snapshot_.device_status_valid = false;
    snapshot_.last_error = error;
}

void Diagnostics::mark_measurement_started()
{
    snapshot_.measurement_running = true;
    snapshot_.last_error = ESP_OK;
}

void Diagnostics::mark_detection_failure(const esp_err_t error)
{
    snapshot_.sensor_present = false;
    snapshot_.measurement_running = false;
    snapshot_.device_status_valid = false;
    snapshot_.last_error = error;
    ++snapshot_.detection_failures;
}

void Diagnostics::mark_communication_failure(const esp_err_t error)
{
    snapshot_.last_error = error;
    ++snapshot_.communication_failures;
}

void Diagnostics::mark_crc_failure()
{
    snapshot_.last_error = ESP_ERR_INVALID_CRC;
    ++snapshot_.crc_failures;
}

void Diagnostics::mark_measurement_success()
{
    snapshot_.sensor_present = true;
    snapshot_.measurement_running = true;
    snapshot_.first_measurement_received = true;
    snapshot_.last_error = ESP_OK;
    ++snapshot_.successful_measurements;
    snapshot_.last_success_us = esp_timer_get_time();
}

void Diagnostics::mark_device_status(const std::uint32_t status)
{
    snapshot_.device_status = status;
    snapshot_.device_status_valid = true;
}

void Diagnostics::mark_device_status_unavailable()
{
    snapshot_.device_status_valid = false;
}

const Snapshot& Diagnostics::snapshot() const
{
    return snapshot_;
}

const char* to_string(const SensorState state)
{
    switch (state) {
    case SensorState::kUninitialized:
        return "uninitialized";
    case SensorState::kDetecting:
        return "detecting";
    case SensorState::kWaitingForFirstMeasurement:
        return "waiting_first_measurement";
    case SensorState::kRunning:
        return "running";
    case SensorState::kOffline:
        return "offline";
    }
    return "unknown";
}

}  // namespace diagnostics
