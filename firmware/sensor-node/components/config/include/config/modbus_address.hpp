#pragma once

#include <cstdint>

#include "esp_err.h"

namespace config {

inline constexpr std::uint8_t kMinimumModbusSlaveAddress = 1;
inline constexpr std::uint8_t kMaximumModbusSlaveAddress = 247;

[[nodiscard]] constexpr bool valid_modbus_slave_address(
    const std::uint16_t address)
{
    return address >= kMinimumModbusSlaveAddress &&
           address <= kMaximumModbusSlaveAddress;
}

// Loads the locally provisioned address from NVS. If no value has been
// provisioned, returns the validated build-time default.
esp_err_t load_modbus_slave_address(std::uint8_t& address);

}  // namespace config
