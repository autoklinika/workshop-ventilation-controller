#pragma once

#include <cstdint>

#include "driver/gpio.h"
#include "driver/i2c_types.h"

namespace config::board {

inline constexpr i2c_port_num_t kI2cPort = I2C_NUM_0;
inline constexpr gpio_num_t kI2cSda = GPIO_NUM_33;
inline constexpr gpio_num_t kI2cScl = GPIO_NUM_32;
inline constexpr std::uint32_t kI2cFrequencyHz = 100'000;
inline constexpr std::uint32_t kI2cTimeoutMs = 100;
inline constexpr bool kEnableInternalI2cPullups = false;

inline constexpr std::uint8_t kSen55Address = 0x69;

inline constexpr gpio_num_t kStatusLed = GPIO_NUM_2;
inline constexpr std::uint32_t kStatusLedActiveLevel = 1;

// Reserved for a later stage. They are documented here to prevent accidental use.
inline constexpr gpio_num_t kRs485Rx = GPIO_NUM_27;
inline constexpr gpio_num_t kRs485Tx = GPIO_NUM_25;
inline constexpr gpio_num_t kRs485Direction = GPIO_NUM_26;

}  // namespace config::board
