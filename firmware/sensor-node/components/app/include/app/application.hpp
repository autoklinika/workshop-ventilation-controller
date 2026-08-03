#pragma once

#include <cstdint>

#include "diagnostics/diagnostics.hpp"
#include "drivers/i2c_bus.hpp"
#include "platform/ota_health_guard.hpp"
#include "platform/status_led.hpp"
#include "sen55/sen55.hpp"
#include "services/sensor_service.hpp"

namespace app {

class Application final {
public:
    Application();
    [[noreturn]] void run();

private:
    esp_err_t initialize();
    void update_status_led();
    void log_measurement_if_new();
    void fatal_restart(esp_err_t error, const char* operation);

    diagnostics::Diagnostics diagnostics_{};
    drivers::I2cBus i2c_bus_{};
    drivers::I2cDevice sen55_i2c_device_{};
    sen55::Sen55 sen55_;
    services::SensorService sensor_service_;
    platform::StatusLed status_led_{};
    platform::OtaHealthGuard ota_health_guard_{};
    std::uint64_t last_logged_sequence_{0};
    std::int64_t last_led_toggle_us_{0};
    bool led_state_{false};
};

}  // namespace app
