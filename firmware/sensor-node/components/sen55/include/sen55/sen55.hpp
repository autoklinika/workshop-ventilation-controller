#pragma once

#include <cstddef>
#include <cstdint>

#include "drivers/i2c_bus.hpp"
#include "esp_err.h"
#include "sen55/sen55_types.hpp"

namespace sen55 {

class Sen55 final {
public:
    Sen55(drivers::I2cBus& bus, drivers::I2cDevice& device);

    esp_err_t probe() const;
    esp_err_t read_device_info(DeviceInfo& info) const;
    esp_err_t start_measurement() const;
    esp_err_t stop_measurement() const;
    esp_err_t data_ready(bool& ready) const;
    esp_err_t read_measurement(Measurement& measurement) const;

private:
    esp_err_t send_command(std::uint16_t command, std::uint32_t post_delay_ms) const;
    esp_err_t read_command(std::uint16_t command,
                           std::uint8_t* response,
                           std::size_t response_size,
                           std::uint32_t processing_delay_ms) const;

    drivers::I2cBus& bus_;
    drivers::I2cDevice& device_;
};

}  // namespace sen55
