#pragma once

#include <array>
#include <cstdint>

namespace sen55 {

struct DeviceVersion {
    std::uint8_t firmware_major{0};
    std::uint8_t firmware_minor{0};
    bool firmware_debug{false};
    std::uint8_t hardware_major{0};
    std::uint8_t hardware_minor{0};
    std::uint8_t protocol_major{0};
    std::uint8_t protocol_minor{0};
};

struct DeviceInfo {
    std::array<char, 33> product_name{};
    DeviceVersion version{};
};

enum MeasurementAvailability : std::uint16_t {
    kPm1Available = 1U << 0U,
    kPm2_5Available = 1U << 1U,
    kPm4Available = 1U << 2U,
    kPm10Available = 1U << 3U,
    kHumidityAvailable = 1U << 4U,
    kTemperatureAvailable = 1U << 5U,
    kVocAvailable = 1U << 6U,
    kNoxAvailable = 1U << 7U,
};

struct Measurement {
    float pm1_0{0.0F};
    float pm2_5{0.0F};
    float pm4_0{0.0F};
    float pm10_0{0.0F};
    float humidity_percent{0.0F};
    float temperature_celsius{0.0F};
    float voc_index{0.0F};
    float nox_index{0.0F};
    std::uint16_t availability_mask{0};
    std::uint64_t sequence{0};
    std::int64_t timestamp_us{0};

    [[nodiscard]] bool available(MeasurementAvailability field) const
    {
        return (availability_mask & static_cast<std::uint16_t>(field)) != 0U;
    }
};

}  // namespace sen55
