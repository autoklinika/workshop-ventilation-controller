#pragma once

#include "esp_log.h"

namespace logging {

void initialize();

}  // namespace logging

#define LOG_ERROR(tag, format, ...) ESP_LOGE(tag, format, ##__VA_ARGS__)
#define LOG_WARN(tag, format, ...) ESP_LOGW(tag, format, ##__VA_ARGS__)
#define LOG_INFO(tag, format, ...) ESP_LOGI(tag, format, ##__VA_ARGS__)
#define LOG_DEBUG(tag, format, ...) ESP_LOGD(tag, format, ##__VA_ARGS__)
