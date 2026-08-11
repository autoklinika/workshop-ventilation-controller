#pragma once

#include <cstdint>

#include "diagnostics/diagnostics.hpp"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"
#include "modbus/register_map.hpp"
#include "sen55/sen55_types.hpp"

namespace modbus {

struct Activity {
    bool monitor_ready{false};
    std::uint32_t request_count{0};
    std::int64_t last_request_us{0};
    std::uint32_t service_error_count{0};
};

class ModbusRtuSlave final {
public:
    ModbusRtuSlave() = default;
    ~ModbusRtuSlave();

    ModbusRtuSlave(const ModbusRtuSlave&) = delete;
    ModbusRtuSlave& operator=(const ModbusRtuSlave&) = delete;

    esp_err_t initialize(std::uint8_t slave_address);
    esp_err_t refresh(const sen55::Measurement& measurement,
                      const diagnostics::Snapshot& snapshot);

    [[nodiscard]] bool initialized() const;
    [[nodiscard]] std::uint8_t slave_address() const;
    [[nodiscard]] std::uint32_t service_error_count() const;
    [[nodiscard]] Activity activity() const;
    [[nodiscard]] const InputRegisterBank& register_bank() const;

private:
    RegisterSource build_source(const sen55::Measurement& measurement,
                                const diagnostics::Snapshot& snapshot,
                                std::int64_t now_us) const;
    static void monitor_task_entry(void* context);
    void monitor_requests();
    void record_service_error(esp_err_t error, const char* operation);
    void destroy();

    void* handle_{nullptr};
    void* monitor_task_{nullptr};
    InputRegisterBank registers_{};
    std::uint8_t slave_address_{0};
    mutable portMUX_TYPE activity_lock_ = portMUX_INITIALIZER_UNLOCKED;
    Activity activity_{};
    std::int64_t last_refresh_us_{0};
};

}  // namespace modbus
