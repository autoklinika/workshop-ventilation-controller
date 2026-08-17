#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace modbus {

inline constexpr std::uint16_t kRegisterMapVersion = 1;
inline constexpr std::size_t kInputRegisterCount = 19;

enum class InputRegister : std::size_t {
    kPm1_0 = 0,
    kPm2_5 = 1,
    kPm4_0 = 2,
    kPm10_0 = 3,
    kHumidity = 4,
    kTemperature = 5,
    kVocIndex = 6,
    kNoxIndex = 7,
    kAvailabilityMask = 8,
    kNodeStatus = 9,
    kMeasurementAgeSeconds = 10,
    kSensorErrorCount = 11,
    kModbusServiceErrorCount = 12,
    kUptimeHigh = 13,
    kUptimeLow = 14,
    kFirmwareVersion = 15,
    kRegisterMapVersion = 16,
    kMeasurementSequenceHigh = 17,
    kMeasurementSequenceLow = 18,
};

enum NodeStatusBit : std::uint16_t {
    kMeasurementValid = 1U << 0,
    kSensorPresent = 1U << 1,
    kMeasurementStale = 1U << 2,
    kI2cError = 1U << 3,
    kDataError = 1U << 4,
    kInitializing = 1U << 5,
    kSensorOffline = 1U << 6,
    kPlatformFault = 1U << 7,

    // Backwards-compatible extension of register 9. Old CM5 software masks
    // the low byte and therefore safely ignores these bits.
    kSen55DeviceStatusSupported = 1U << 8,
    kSen55DeviceStatusValid = 1U << 9,
    kSen55FanSpeedWarning = 1U << 10,
    kSen55FanCleaning = 1U << 11,
    kSen55GasSensorError = 1U << 12,
    kSen55RhtError = 1U << 13,
    kSen55LaserError = 1U << 14,
    kSen55FanError = 1U << 15,
};

struct RegisterSource {
    float pm1_0{0.0F};
    float pm2_5{0.0F};
    float pm4_0{0.0F};
    float pm10_0{0.0F};
    float humidity_percent{0.0F};
    float temperature_celsius{0.0F};
    float voc_index{0.0F};
    float nox_index{0.0F};
    std::uint8_t availability_mask{0};

    bool measurement_valid{false};
    bool sensor_present{false};
    bool measurement_stale{true};
    bool i2c_error{false};
    bool data_error{false};
    bool initializing{true};
    bool sensor_offline{false};
    bool platform_fault{false};

    bool sen55_device_status_supported{false};
    bool sen55_device_status_valid{false};
    std::uint32_t sen55_device_status{0};

    std::uint16_t measurement_age_seconds{0xFFFFU};
    std::uint32_t sensor_error_count{0};
    std::uint32_t modbus_service_error_count{0};
    std::uint32_t uptime_seconds{0};
    std::uint16_t firmware_version{0};
    std::uint64_t measurement_sequence{0};
};

using InputRegisterBank = std::array<std::uint16_t, kInputRegisterCount>;

[[nodiscard]] InputRegisterBank encode_input_registers(const RegisterSource& source);

}  // namespace modbus
