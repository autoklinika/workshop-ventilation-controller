#pragma once

#include <cstddef>
#include <cstdint>

#include "driver/i2c_master.h"
#include "esp_err.h"

namespace drivers {

class I2cBus final {
public:
    I2cBus() = default;
    ~I2cBus();

    I2cBus(const I2cBus&) = delete;
    I2cBus& operator=(const I2cBus&) = delete;

    esp_err_t initialize();
    esp_err_t probe(std::uint8_t address, std::uint32_t timeout_ms) const;

    [[nodiscard]] i2c_master_bus_handle_t handle() const;
    [[nodiscard]] bool initialized() const;

private:
    i2c_master_bus_handle_t handle_{nullptr};
};

class I2cDevice final {
public:
    I2cDevice() = default;
    ~I2cDevice();

    I2cDevice(const I2cDevice&) = delete;
    I2cDevice& operator=(const I2cDevice&) = delete;

    esp_err_t initialize(I2cBus& bus, std::uint8_t address, std::uint32_t frequency_hz);
    esp_err_t write(const std::uint8_t* data, std::size_t size, std::uint32_t timeout_ms) const;
    esp_err_t read(std::uint8_t* data, std::size_t size, std::uint32_t timeout_ms) const;
    esp_err_t write_then_read(const std::uint8_t* tx_data,
                              std::size_t tx_size,
                              std::uint8_t* rx_data,
                              std::size_t rx_size,
                              std::uint32_t processing_delay_ms,
                              std::uint32_t timeout_ms) const;

    [[nodiscard]] bool initialized() const;

private:
    i2c_master_dev_handle_t handle_{nullptr};
};

}  // namespace drivers
