#include "sen55/sen55.hpp"

#include <algorithm>
#include <array>
#include <cstring>

#include "config/board_config.hpp"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "logging/log.hpp"
#include "sen55/sen55_crc.hpp"

namespace sen55 {
namespace {
constexpr char kTag[] = "sen55";

constexpr std::uint16_t kStartMeasurementCommand = 0x0021;
constexpr std::uint16_t kStopMeasurementCommand = 0x0104;
constexpr std::uint16_t kReadDataReadyCommand = 0x0202;
constexpr std::uint16_t kReadMeasuredValuesCommand = 0x03C4;
constexpr std::uint16_t kGetProductNameCommand = 0xD014;
constexpr std::uint16_t kGetVersionCommand = 0xD100;

constexpr std::uint16_t kUnavailableUnsigned = 0xFFFF;
constexpr std::int16_t kUnavailableSigned = 0x7FFF;

std::uint16_t read_u16_be(const std::uint8_t* data)
{
    return static_cast<std::uint16_t>((static_cast<std::uint16_t>(data[0]) << 8U) | data[1]);
}

std::int16_t read_i16_be(const std::uint8_t* data)
{
    return static_cast<std::int16_t>(read_u16_be(data));
}

void set_unsigned_measurement(const std::uint16_t raw,
                              const float divisor,
                              const MeasurementAvailability field,
                              float& output,
                              std::uint16_t& mask)
{
    if (raw != kUnavailableUnsigned) {
        output = static_cast<float>(raw) / divisor;
        mask |= static_cast<std::uint16_t>(field);
    }
}

void set_signed_measurement(const std::int16_t raw,
                            const float divisor,
                            const MeasurementAvailability field,
                            float& output,
                            std::uint16_t& mask)
{
    if (raw != kUnavailableSigned) {
        output = static_cast<float>(raw) / divisor;
        mask |= static_cast<std::uint16_t>(field);
    }
}
}  // namespace

Sen55::Sen55(drivers::I2cBus& bus, drivers::I2cDevice& device) : bus_(bus), device_(device) {}

esp_err_t Sen55::probe() const
{
    return bus_.probe(config::board::kSen55Address, config::board::kI2cTimeoutMs);
}

esp_err_t Sen55::read_device_info(DeviceInfo& info) const
{
    std::array<std::uint8_t, 48> product_response{};
    esp_err_t result = read_command(kGetProductNameCommand,
                                    product_response.data(),
                                    product_response.size(),
                                    20);
    if (result != ESP_OK) {
        return result;
    }

    std::array<std::uint8_t, 32> product_payload{};
    result = decode_crc_words(product_response.data(),
                              product_response.size(),
                              product_payload.data(),
                              product_payload.size());
    if (result != ESP_OK) {
        return result;
    }

    std::fill(info.product_name.begin(), info.product_name.end(), '\0');
    const auto terminator = std::find(product_payload.begin(), product_payload.end(), 0U);
    const std::size_t product_length = static_cast<std::size_t>(terminator - product_payload.begin());
    std::memcpy(info.product_name.data(), product_payload.data(), product_length);

    std::array<std::uint8_t, 12> version_response{};
    result = read_command(kGetVersionCommand,
                          version_response.data(),
                          version_response.size(),
                          20);
    if (result != ESP_OK) {
        return result;
    }

    std::array<std::uint8_t, 8> version_payload{};
    result = decode_crc_words(version_response.data(),
                              version_response.size(),
                              version_payload.data(),
                              version_payload.size());
    if (result != ESP_OK) {
        return result;
    }

    info.version.firmware_major = version_payload[0];
    info.version.firmware_minor = version_payload[1];
    info.version.firmware_debug = version_payload[2] != 0U;
    info.version.hardware_major = version_payload[3];
    info.version.hardware_minor = version_payload[4];
    info.version.protocol_major = version_payload[5];
    info.version.protocol_minor = version_payload[6];
    return ESP_OK;
}

esp_err_t Sen55::start_measurement() const
{
    return send_command(kStartMeasurementCommand, 50);
}

esp_err_t Sen55::stop_measurement() const
{
    return send_command(kStopMeasurementCommand, 160);
}

esp_err_t Sen55::data_ready(bool& ready) const
{
    std::array<std::uint8_t, 3> response{};
    esp_err_t result = read_command(kReadDataReadyCommand, response.data(), response.size(), 20);
    if (result != ESP_OK) {
        return result;
    }

    std::array<std::uint8_t, 2> payload{};
    result = decode_crc_words(response.data(), response.size(), payload.data(), payload.size());
    if (result != ESP_OK) {
        return result;
    }

    ready = payload[1] != 0U;
    return ESP_OK;
}

esp_err_t Sen55::read_measurement(Measurement& measurement) const
{
    std::array<std::uint8_t, 24> response{};
    esp_err_t result = read_command(kReadMeasuredValuesCommand, response.data(), response.size(), 20);
    if (result != ESP_OK) {
        return result;
    }

    std::array<std::uint8_t, 16> payload{};
    result = decode_crc_words(response.data(), response.size(), payload.data(), payload.size());
    if (result != ESP_OK) {
        return result;
    }

    Measurement parsed{};
    set_unsigned_measurement(read_u16_be(&payload[0]), 10.0F, kPm1Available, parsed.pm1_0, parsed.availability_mask);
    set_unsigned_measurement(read_u16_be(&payload[2]), 10.0F, kPm2_5Available, parsed.pm2_5, parsed.availability_mask);
    set_unsigned_measurement(read_u16_be(&payload[4]), 10.0F, kPm4Available, parsed.pm4_0, parsed.availability_mask);
    set_unsigned_measurement(read_u16_be(&payload[6]), 10.0F, kPm10Available, parsed.pm10_0, parsed.availability_mask);
    set_signed_measurement(read_i16_be(&payload[8]), 100.0F, kHumidityAvailable, parsed.humidity_percent, parsed.availability_mask);
    set_signed_measurement(read_i16_be(&payload[10]), 200.0F, kTemperatureAvailable, parsed.temperature_celsius, parsed.availability_mask);
    set_signed_measurement(read_i16_be(&payload[12]), 10.0F, kVocAvailable, parsed.voc_index, parsed.availability_mask);
    set_signed_measurement(read_i16_be(&payload[14]), 10.0F, kNoxAvailable, parsed.nox_index, parsed.availability_mask);
    parsed.timestamp_us = esp_timer_get_time();

    measurement = parsed;
    return ESP_OK;
}

esp_err_t Sen55::send_command(const std::uint16_t command, const std::uint32_t post_delay_ms) const
{
    const std::array<std::uint8_t, 2> command_bytes{
        static_cast<std::uint8_t>((command >> 8U) & 0xFFU),
        static_cast<std::uint8_t>(command & 0xFFU),
    };

    const esp_err_t result = device_.write(command_bytes.data(),
                                            command_bytes.size(),
                                            config::board::kI2cTimeoutMs);
    if (result == ESP_OK && post_delay_ms > 0) {
        vTaskDelay(pdMS_TO_TICKS(post_delay_ms));
    }
    return result;
}

esp_err_t Sen55::read_command(const std::uint16_t command,
                              std::uint8_t* response,
                              const std::size_t response_size,
                              const std::uint32_t processing_delay_ms) const
{
    const std::array<std::uint8_t, 2> command_bytes{
        static_cast<std::uint8_t>((command >> 8U) & 0xFFU),
        static_cast<std::uint8_t>(command & 0xFFU),
    };

    const esp_err_t result = device_.write_then_read(command_bytes.data(),
                                                      command_bytes.size(),
                                                      response,
                                                      response_size,
                                                      processing_delay_ms,
                                                      config::board::kI2cTimeoutMs);
    if (result != ESP_OK) {
        LOG_DEBUG(kTag, "command 0x%04X failed: %s", command, esp_err_to_name(result));
    }
    return result;
}

}  // namespace sen55
