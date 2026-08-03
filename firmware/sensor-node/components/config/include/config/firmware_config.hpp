#pragma once

#include <cstdint>

namespace config::firmware {

inline constexpr char kProjectName[] = "kamod-sen55-sensor-node";
inline constexpr char kVersion[] = "0.2.0-stage2";
inline constexpr std::uint16_t kFirmwareVersionPacked = 0x0002;

inline constexpr std::uint32_t kApplicationLoopPeriodMs = 100;
inline constexpr std::uint32_t kSensorPollPeriodMs = 200;
inline constexpr std::uint32_t kSensorReconnectPeriodMs = 5'000;
inline constexpr std::uint32_t kFirstMeasurementTimeoutMs = 10'000;
inline constexpr std::uint32_t kMeasurementStaleAfterMs = 5'000;
inline constexpr std::uint32_t kOtaConfirmationDelayMs = 30'000;
inline constexpr std::uint32_t kMaximumConsecutiveReadErrors = 3;

inline constexpr std::uint8_t kModbusSlaveAddress = 1;
inline constexpr std::uint32_t kModbusBaudRate = 19'200;
inline constexpr std::uint32_t kModbusRegisterRefreshPeriodMs = 250;

}  // namespace config::firmware
