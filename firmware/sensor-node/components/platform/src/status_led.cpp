#include "platform/status_led.hpp"

#include <cstdint>

#include "config/board_config.hpp"
#include "driver/gpio.h"
#include "logging/log.hpp"

namespace platform {
namespace {
constexpr char kTag[] = "gpio";
}

esp_err_t StatusLed::initialize()
{
    gpio_config_t gpio_cfg{};
    gpio_cfg.pin_bit_mask = 1ULL << static_cast<std::uint32_t>(config::board::kStatusLed);
    gpio_cfg.mode = GPIO_MODE_OUTPUT;
    gpio_cfg.pull_up_en = GPIO_PULLUP_DISABLE;
    gpio_cfg.pull_down_en = GPIO_PULLDOWN_DISABLE;
    gpio_cfg.intr_type = GPIO_INTR_DISABLE;

    esp_err_t result = gpio_config(&gpio_cfg);
    if (result != ESP_OK) {
        LOG_ERROR(kTag, "status LED GPIO initialization failed: %s", esp_err_to_name(result));
        return result;
    }

    initialized_ = true;
    result = set(false);
    if (result == ESP_OK) {
        LOG_INFO(kTag, "status LED initialized on GPIO%d", static_cast<int>(config::board::kStatusLed));
    }
    return result;
}

esp_err_t StatusLed::set(const bool enabled) const
{
    if (!initialized_) {
        return ESP_ERR_INVALID_STATE;
    }
    const int level = enabled ? static_cast<int>(config::board::kStatusLedActiveLevel)
                              : 1 - static_cast<int>(config::board::kStatusLedActiveLevel);
    return gpio_set_level(config::board::kStatusLed, level);
}

}  // namespace platform
