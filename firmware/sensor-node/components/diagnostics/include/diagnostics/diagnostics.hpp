#pragma once

#include <cstdint>

#include "esp_err.h"

namespace diagnostics {

enum class SensorState : std::uint8_t {
    kUninitialized,
    kDetecting,
    kWaitingForFirstMeasurement,
    kRunning,
    kOffline,
};

struct Snapshot {
    bool gpio_ready{false};
    bool i2c_ready{false};
    bool rs485_ready{false};
    bool sensor_present{false};
    bool measurement_running{false};
    bool first_measurement_received{false};
    SensorState sensor_state{SensorState::kUninitialized};
    esp_err_t last_error{ESP_OK};
    std::uint32_t detection_failures{0};
    std::uint32_t communication_failures{0};
    std::uint32_t crc_failures{0};
    std::uint32_t successful_measurements{0};
    std::int64_t last_success_us{0};
};

class Diagnostics final {
public:
    void mark_gpio_ready();
    void mark_i2c_ready();
    void mark_rs485_ready();
    void set_sensor_state(SensorState state);
    void mark_sensor_detected();
    void mark_sensor_offline(esp_err_t error);
    void mark_measurement_started();
    void mark_detection_failure(esp_err_t error);
    void mark_communication_failure(esp_err_t error);
    void mark_crc_failure();
    void mark_measurement_success();

    [[nodiscard]] const Snapshot& snapshot() const;

private:
    Snapshot snapshot_{};
};

const char* to_string(SensorState state);

}  // namespace diagnostics
