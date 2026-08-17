#pragma once

#include <cstdint>

#include "sdkconfig.h"

namespace config::firmware {

inline constexpr char kProjectName[] = "kamod-sen55-sensor-node";
#ifdef CONFIG_WVC_OTA_ROLLBACK_TEST_IMAGE
inline constexpr char kVersion[] = "0.6.1-stage1-rollback-test";
#else
inline constexpr char kVersion[] = "0.6.0-stage1-sen55-status";
#endif
inline constexpr std::uint16_t kFirmwareVersionPacked = 0x0006;

inline constexpr std::uint32_t kApplicationLoopPeriodMs = 100;
inline constexpr std::uint32_t kSensorPollPeriodMs = 200;
inline constexpr std::uint32_t kSensorReconnectPeriodMs = 5'000;
inline constexpr std::uint32_t kFirstMeasurementTimeoutMs = 10'000;
inline constexpr std::uint32_t kMeasurementStaleAfterMs = 5'000;
inline constexpr std::uint32_t kOtaConfirmationDelayMs = 30'000;
inline constexpr std::uint32_t kOtaRollbackTestRestartDelayMs = 15'000;
inline constexpr std::uint32_t kMaximumConsecutiveReadErrors = 3;

inline constexpr std::uint32_t kModbusBaudRate = 19'200;
inline constexpr std::uint32_t kModbusRegisterRefreshPeriodMs = 250;

}  // namespace config::firmware
