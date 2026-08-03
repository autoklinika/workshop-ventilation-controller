#pragma once

#include <cstdint>

namespace config::firmware {

inline constexpr char kProjectName[] = "kamod-sen55-sensor-node";
inline constexpr char kVersion[] = "0.1.0-stage1";

inline constexpr std::uint32_t kApplicationLoopPeriodMs = 100;
inline constexpr std::uint32_t kSensorPollPeriodMs = 200;
inline constexpr std::uint32_t kSensorReconnectPeriodMs = 5'000;
inline constexpr std::uint32_t kFirstMeasurementTimeoutMs = 10'000;
inline constexpr std::uint32_t kOtaConfirmationDelayMs = 30'000;
inline constexpr std::uint32_t kMaximumConsecutiveReadErrors = 3;

}  // namespace config::firmware
