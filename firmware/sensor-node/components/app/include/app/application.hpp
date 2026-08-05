#pragma once

#include <cstdint>

#include "config/service_credentials.hpp"
#include "diagnostics/diagnostics.hpp"
#include "drivers/i2c_bus.hpp"
#include "modbus/modbus_rtu_slave.hpp"
#include "platform/ota_health_guard.hpp"
#include "platform/status_led.hpp"
#include "sen55/sen55.hpp"
#include "service_wifi/service_wifi.hpp"
#include "services/sensor_service.hpp"

namespace app {

class Application final {
public:
    Application();
    [[noreturn]] void run();

private:
    esp_err_t initialize();
    void start_optional_service_wifi();
    void publish_service_snapshot();
    void update_status_led();
    void log_measurement_if_new();
    void fatal_restart(esp_err_t error, const char* operation);

    diagnostics::Diagnostics diagnostics_{};
    drivers::I2cBus i2c_bus_{};
    drivers::I2cDevice sen55_i2c_device_{};
    sen55::Sen55 sen55_;
    services::SensorService sensor_service_;
    modbus::ModbusRtuSlave modbus_slave_{};
    platform::StatusLed status_led_{};
    platform::OtaHealthGuard ota_health_guard_{};
    service_wifi::ServiceWifi service_wifi_{};
    config::ServiceCredentials service_credentials_{};
    bool service_credentials_available_{false};
    std::uint64_t last_logged_sequence_{0};
    std::int64_t last_led_toggle_us_{0};
    bool led_state_{false};
};

}  // namespace app
