#include "modbus/register_map.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

namespace modbus {
namespace {

constexpr std::uint8_t kPm1Available = 1U << 0;
constexpr std::uint8_t kPm2_5Available = 1U << 1;
constexpr std::uint8_t kPm4Available = 1U << 2;
constexpr std::uint8_t kPm10Available = 1U << 3;
constexpr std::uint8_t kHumidityAvailable = 1U << 4;
constexpr std::uint8_t kTemperatureAvailable = 1U << 5;
constexpr std::uint8_t kVocAvailable = 1U << 6;
constexpr std::uint8_t kNoxAvailable = 1U << 7;

std::uint16_t saturate_u16(const std::uint32_t value)
{
    return static_cast<std::uint16_t>(std::min<std::uint32_t>(
        value, std::numeric_limits<std::uint16_t>::max()));
}

std::uint16_t encode_unsigned(const float value,
                              const float scale,
                              const bool available)
{
    if (!available || !std::isfinite(value)) {
        return 0;
    }

    const double scaled = std::round(static_cast<double>(value) * scale);
    const double clamped = std::clamp(
        scaled,
        0.0,
        static_cast<double>(std::numeric_limits<std::uint16_t>::max()));
    return static_cast<std::uint16_t>(clamped);
}

std::uint16_t encode_signed(const float value,
                            const float scale,
                            const bool available)
{
    if (!available || !std::isfinite(value)) {
        return 0;
    }

    const double scaled = std::round(static_cast<double>(value) * scale);
    const double clamped = std::clamp(
        scaled,
        static_cast<double>(std::numeric_limits<std::int16_t>::min()),
        static_cast<double>(std::numeric_limits<std::int16_t>::max()));
    const auto signed_value = static_cast<std::int16_t>(clamped);
    return static_cast<std::uint16_t>(signed_value);
}

void put(InputRegisterBank& bank,
         const InputRegister reg,
         const std::uint16_t value)
{
    bank[static_cast<std::size_t>(reg)] = value;
}

}  // namespace

InputRegisterBank encode_input_registers(const RegisterSource& source)
{
    InputRegisterBank registers{};

    put(registers,
        InputRegister::kPm1_0,
        encode_unsigned(source.pm1_0,
                        10.0F,
                        (source.availability_mask & kPm1Available) != 0));
    put(registers,
        InputRegister::kPm2_5,
        encode_unsigned(source.pm2_5,
                        10.0F,
                        (source.availability_mask & kPm2_5Available) != 0));
    put(registers,
        InputRegister::kPm4_0,
        encode_unsigned(source.pm4_0,
                        10.0F,
                        (source.availability_mask & kPm4Available) != 0));
    put(registers,
        InputRegister::kPm10_0,
        encode_unsigned(source.pm10_0,
                        10.0F,
                        (source.availability_mask & kPm10Available) != 0));
    put(registers,
        InputRegister::kHumidity,
        encode_unsigned(source.humidity_percent,
                        100.0F,
                        (source.availability_mask & kHumidityAvailable) != 0));
    put(registers,
        InputRegister::kTemperature,
        encode_signed(source.temperature_celsius,
                      100.0F,
                      (source.availability_mask & kTemperatureAvailable) != 0));
    put(registers,
        InputRegister::kVocIndex,
        encode_unsigned(source.voc_index,
                        10.0F,
                        (source.availability_mask & kVocAvailable) != 0));
    put(registers,
        InputRegister::kNoxIndex,
        encode_unsigned(source.nox_index,
                        10.0F,
                        (source.availability_mask & kNoxAvailable) != 0));

    put(registers, InputRegister::kAvailabilityMask, source.availability_mask);

    std::uint16_t status = 0;
    status |= source.measurement_valid ? kMeasurementValid : 0;
    status |= source.sensor_present ? kSensorPresent : 0;
    status |= source.measurement_stale ? kMeasurementStale : 0;
    status |= source.i2c_error ? kI2cError : 0;
    status |= source.data_error ? kDataError : 0;
    status |= source.initializing ? kInitializing : 0;
    status |= source.sensor_offline ? kSensorOffline : 0;
    status |= source.platform_fault ? kPlatformFault : 0;
    put(registers, InputRegister::kNodeStatus, status);

    put(registers,
        InputRegister::kMeasurementAgeSeconds,
        source.measurement_age_seconds);
    put(registers,
        InputRegister::kSensorErrorCount,
        saturate_u16(source.sensor_error_count));
    put(registers,
        InputRegister::kModbusServiceErrorCount,
        saturate_u16(source.modbus_service_error_count));

    put(registers,
        InputRegister::kUptimeHigh,
        static_cast<std::uint16_t>(source.uptime_seconds >> 16U));
    put(registers,
        InputRegister::kUptimeLow,
        static_cast<std::uint16_t>(source.uptime_seconds & 0xFFFFU));
    put(registers, InputRegister::kFirmwareVersion, source.firmware_version);
    put(registers, InputRegister::kRegisterMapVersion, kRegisterMapVersion);

    const auto sequence_low_32 = static_cast<std::uint32_t>(source.measurement_sequence);
    put(registers,
        InputRegister::kMeasurementSequenceHigh,
        static_cast<std::uint16_t>(sequence_low_32 >> 16U));
    put(registers,
        InputRegister::kMeasurementSequenceLow,
        static_cast<std::uint16_t>(sequence_low_32 & 0xFFFFU));

    return registers;
}

}  // namespace modbus
