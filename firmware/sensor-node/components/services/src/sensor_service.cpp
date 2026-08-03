#include "services/sensor_service.hpp"

#include "config/firmware_config.hpp"
#include "esp_timer.h"
#include "logging/log.hpp"

namespace services {
namespace {
constexpr char kTag[] = "sensor_service";

std::int64_t elapsed_ms(const std::int64_t since_us)
{
    return (esp_timer_get_time() - since_us) / 1000;
}
}  // namespace

SensorService::SensorService(sen55::Sen55& sensor, diagnostics::Diagnostics& diagnostics)
    : sensor_(sensor), diagnostics_(diagnostics)
{
}

void SensorService::start()
{
    diagnostics_.set_sensor_state(diagnostics::SensorState::kDetecting);
    connect();
}

void SensorService::poll()
{
    const auto state = diagnostics_.snapshot().sensor_state;
    if (state == diagnostics::SensorState::kOffline || state == diagnostics::SensorState::kDetecting) {
        if (elapsed_ms(last_connect_attempt_us_) >= config::firmware::kSensorReconnectPeriodMs) {
            connect();
        }
        return;
    }

    if (elapsed_ms(last_poll_us_) < config::firmware::kSensorPollPeriodMs) {
        return;
    }
    last_poll_us_ = esp_timer_get_time();

    bool ready = false;
    esp_err_t result = sensor_.data_ready(ready);
    if (result != ESP_OK) {
        handle_error(result, "read_data_ready");
        return;
    }

    consecutive_errors_ = 0;
    if (!ready) {
        if (state == diagnostics::SensorState::kWaitingForFirstMeasurement &&
            elapsed_ms(state_started_us_) > config::firmware::kFirstMeasurementTimeoutMs) {
            handle_error(ESP_ERR_TIMEOUT, "wait_first_measurement");
        }
        return;
    }

    sen55::Measurement measurement{};
    result = sensor_.read_measurement(measurement);
    if (result != ESP_OK) {
        handle_error(result, "read_measurement");
        return;
    }

    measurement.sequence = ++sequence_;
    latest_measurement_ = measurement;
    consecutive_errors_ = 0;
    diagnostics_.mark_measurement_success();
    diagnostics_.set_sensor_state(diagnostics::SensorState::kRunning);
}

bool SensorService::online() const
{
    return diagnostics_.snapshot().sensor_state == diagnostics::SensorState::kRunning;
}

bool SensorService::has_new_measurement(const std::uint64_t last_sequence) const
{
    return latest_measurement_.sequence > last_sequence;
}

const sen55::Measurement& SensorService::latest_measurement() const
{
    return latest_measurement_;
}

const sen55::DeviceInfo& SensorService::device_info() const
{
    return device_info_;
}

void SensorService::connect()
{
    last_connect_attempt_us_ = esp_timer_get_time();
    diagnostics_.set_sensor_state(diagnostics::SensorState::kDetecting);

    esp_err_t result = sensor_.probe();
    if (result != ESP_OK) {
        diagnostics_.mark_detection_failure(result);
        set_offline(result);
        return;
    }

    diagnostics_.mark_sensor_detected();
    result = sensor_.read_device_info(device_info_);
    if (result != ESP_OK) {
        handle_error(result, "read_device_info");
        return;
    }

    LOG_INFO(kTag,
             "detected product=%s firmware=%u.%u%s hardware=%u.%u protocol=%u.%u",
             device_info_.product_name.data(),
             device_info_.version.firmware_major,
             device_info_.version.firmware_minor,
             device_info_.version.firmware_debug ? "-debug" : "",
             device_info_.version.hardware_major,
             device_info_.version.hardware_minor,
             device_info_.version.protocol_major,
             device_info_.version.protocol_minor);

    result = sensor_.start_measurement();
    if (result != ESP_OK) {
        handle_error(result, "start_measurement");
        return;
    }

    consecutive_errors_ = 0;
    diagnostics_.mark_measurement_started();
    diagnostics_.set_sensor_state(diagnostics::SensorState::kWaitingForFirstMeasurement);
    state_started_us_ = esp_timer_get_time();
    last_poll_us_ = 0;
    LOG_INFO(kTag, "continuous measurement started");
}

void SensorService::handle_error(const esp_err_t error, const char* operation)
{
    if (error == ESP_ERR_INVALID_CRC) {
        diagnostics_.mark_crc_failure();
    } else {
        diagnostics_.mark_communication_failure(error);
    }

    ++consecutive_errors_;
    LOG_WARN(kTag,
             "%s failed: %s consecutive_errors=%lu",
             operation,
             esp_err_to_name(error),
             static_cast<unsigned long>(consecutive_errors_));

    if (consecutive_errors_ >= config::firmware::kMaximumConsecutiveReadErrors) {
        set_offline(error);
    }
}

void SensorService::set_offline(const esp_err_t error)
{
    diagnostics_.mark_sensor_offline(error);
    diagnostics_.set_sensor_state(diagnostics::SensorState::kOffline);
    state_started_us_ = esp_timer_get_time();
    consecutive_errors_ = 0;
    LOG_WARN(kTag,
             "sensor offline: %s; retry in %lu ms",
             esp_err_to_name(error),
             static_cast<unsigned long>(config::firmware::kSensorReconnectPeriodMs));
}

}  // namespace services
