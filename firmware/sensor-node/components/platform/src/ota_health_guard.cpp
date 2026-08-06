#include "platform/ota_health_guard.hpp"

#include "config/firmware_config.hpp"
#include "esp_ota_ops.h"
#include "esp_timer.h"
#include "logging/log.hpp"

namespace platform {
namespace {
constexpr char kTag[] = "ota_health";
}

esp_err_t OtaHealthGuard::initialize()
{
    const esp_partition_t* running = esp_ota_get_running_partition();
    if (running == nullptr) {
        return ESP_ERR_NOT_FOUND;
    }

    esp_ota_img_states_t state{};
    const esp_err_t result = esp_ota_get_state_partition(running, &state);
    if (result == ESP_ERR_NOT_SUPPORTED) {
        LOG_INFO(kTag, "running image has no OTA verification state");
        return ESP_OK;
    }
    if (result != ESP_OK) {
        LOG_WARN(kTag, "cannot read OTA state: %s", esp_err_to_name(result));
        return result;
    }

    pending_ = state == ESP_OTA_IMG_PENDING_VERIFY;
    healthy_since_us_ = 0;
    LOG_INFO(kTag,
             "image_state=%d pending_confirmation=%s",
             static_cast<int>(state),
             pending_ ? "yes" : "no");
    return ESP_OK;
}

esp_err_t OtaHealthGuard::confirm_if_due(const bool platform_healthy)
{
    if (!pending_) {
        return ESP_OK;
    }

    const std::int64_t now_us = esp_timer_get_time();
    if (!platform_healthy) {
        if (healthy_since_us_ != 0) {
            LOG_WARN(kTag, "OTA health window reset because the platform became unhealthy");
        }
        healthy_since_us_ = 0;
        return ESP_OK;
    }

    if (healthy_since_us_ == 0) {
        healthy_since_us_ = now_us;
        LOG_INFO(kTag, "OTA continuous health confirmation window started");
        return ESP_OK;
    }

    const std::int64_t elapsed_ms = (now_us - healthy_since_us_) / 1000;
    if (elapsed_ms < static_cast<std::int64_t>(config::firmware::kOtaConfirmationDelayMs)) {
        return ESP_OK;
    }

    const esp_err_t result = esp_ota_mark_app_valid_cancel_rollback();
    if (result == ESP_OK) {
        pending_ = false;
        healthy_since_us_ = 0;
        LOG_INFO(kTag,
                 "running image confirmed after %lld ms of continuous healthy operation",
                 static_cast<long long>(elapsed_ms));
    } else {
        LOG_ERROR(kTag, "failed to confirm running image: %s", esp_err_to_name(result));
    }
    return result;
}

bool OtaHealthGuard::confirmation_pending() const
{
    return pending_;
}

}  // namespace platform
