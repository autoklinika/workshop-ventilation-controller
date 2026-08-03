#pragma once

#include <cstdint>

#include "diagnostics/diagnostics.hpp"
#include "esp_err.h"
#include "modbus/register_map.hpp"
#include "sen55/sen55_types.hpp"

namespace modbus {

class ModbusRtuSlave final {
public:
    ModbusRtuSlave() = default;
    ~ModbusRtuSlave();

    ModbusRtuSlave(const ModbusRtuSlave&) = delete;
    ModbusRtuSlave& operator=(const ModbusRtuSlave&) = delete;

    esp_err_t initialize();
    esp_err_t refresh(const sen55::Measurement& measurement,
                      const diagnostics::Snapshot& snapshot);

    [[nodiscard]] bool initialized() const;
    [[nodiscard]] std::uint32_t service_error_count() const;
    [[nodiscard]] const InputRegisterBank& register_bank() const;

private:
    RegisterSource build_source(const sen55::Measurement& measurement,
                                const diagnostics::Snapshot& snapshot,
                                std::int64_t now_us) const;
    void record_service_error(esp_err_t error, const char* operation);
    void destroy();

    void* handle_{nullptr};
    InputRegisterBank registers_{};
    std::uint32_t service_error_count_{0};
    std::int64_t last_refresh_us_{0};
};

}  // namespace modbus
