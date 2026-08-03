#include "drivers/i2c_bus.hpp"

#include "config/board_config.hpp"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "logging/log.hpp"

namespace drivers {
namespace {
constexpr char kTag[] = "i2c";
}

I2cBus::~I2cBus()
{
    if (handle_ != nullptr) {
        const esp_err_t result = i2c_del_master_bus(handle_);
        if (result != ESP_OK) {
            LOG_WARN(kTag, "failed to delete I2C bus: %s", esp_err_to_name(result));
        }
    }
}

esp_err_t I2cBus::initialize()
{
    if (handle_ != nullptr) {
        return ESP_OK;
    }

    i2c_master_bus_config_t bus_config{};
    bus_config.i2c_port = config::board::kI2cPort;
    bus_config.sda_io_num = config::board::kI2cSda;
    bus_config.scl_io_num = config::board::kI2cScl;
    bus_config.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_config.glitch_ignore_cnt = 7;
    bus_config.flags.enable_internal_pullup = config::board::kEnableInternalI2cPullups;

    const esp_err_t result = i2c_new_master_bus(&bus_config, &handle_);
    if (result != ESP_OK) {
        LOG_ERROR(kTag, "I2C initialization failed: %s", esp_err_to_name(result));
        handle_ = nullptr;
        return result;
    }

    LOG_INFO(kTag,
             "initialized: port=%d sda=%d scl=%d frequency=%lu internal_pullups=%s",
             static_cast<int>(config::board::kI2cPort),
             static_cast<int>(config::board::kI2cSda),
             static_cast<int>(config::board::kI2cScl),
             static_cast<unsigned long>(config::board::kI2cFrequencyHz),
             config::board::kEnableInternalI2cPullups ? "on" : "off");
    return ESP_OK;
}

esp_err_t I2cBus::probe(const std::uint8_t address, const std::uint32_t timeout_ms) const
{
    if (handle_ == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }
    return i2c_master_probe(handle_, address, static_cast<int>(timeout_ms));
}

i2c_master_bus_handle_t I2cBus::handle() const
{
    return handle_;
}

bool I2cBus::initialized() const
{
    return handle_ != nullptr;
}

I2cDevice::~I2cDevice()
{
    if (handle_ != nullptr) {
        const esp_err_t result = i2c_master_bus_rm_device(handle_);
        if (result != ESP_OK) {
            LOG_WARN(kTag, "failed to remove I2C device: %s", esp_err_to_name(result));
        }
    }
}

esp_err_t I2cDevice::initialize(I2cBus& bus,
                                const std::uint8_t address,
                                const std::uint32_t frequency_hz)
{
    if (handle_ != nullptr) {
        return ESP_OK;
    }
    if (!bus.initialized()) {
        return ESP_ERR_INVALID_STATE;
    }

    i2c_device_config_t device_config{};
    device_config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    device_config.device_address = address;
    device_config.scl_speed_hz = frequency_hz;

    const esp_err_t result = i2c_master_bus_add_device(bus.handle(), &device_config, &handle_);
    if (result != ESP_OK) {
        LOG_ERROR(kTag, "failed to add device 0x%02X: %s", address, esp_err_to_name(result));
        handle_ = nullptr;
    }
    return result;
}

esp_err_t I2cDevice::write(const std::uint8_t* data,
                           const std::size_t size,
                           const std::uint32_t timeout_ms) const
{
    if (handle_ == nullptr || data == nullptr || size == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    return i2c_master_transmit(handle_, data, size, static_cast<int>(timeout_ms));
}

esp_err_t I2cDevice::read(std::uint8_t* data,
                          const std::size_t size,
                          const std::uint32_t timeout_ms) const
{
    if (handle_ == nullptr || data == nullptr || size == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    return i2c_master_receive(handle_, data, size, static_cast<int>(timeout_ms));
}

esp_err_t I2cDevice::write_then_read(const std::uint8_t* tx_data,
                                     const std::size_t tx_size,
                                     std::uint8_t* rx_data,
                                     const std::size_t rx_size,
                                     const std::uint32_t processing_delay_ms,
                                     const std::uint32_t timeout_ms) const
{
    esp_err_t result = write(tx_data, tx_size, timeout_ms);
    if (result != ESP_OK) {
        return result;
    }

    if (processing_delay_ms > 0) {
        vTaskDelay(pdMS_TO_TICKS(processing_delay_ms));
    }

    return read(rx_data, rx_size, timeout_ms);
}

bool I2cDevice::initialized() const
{
    return handle_ != nullptr;
}

}  // namespace drivers
