#include "logging/log.hpp"

namespace logging {

void initialize()
{
    esp_log_level_set("*", ESP_LOG_INFO);
    esp_log_level_set("sen55", ESP_LOG_DEBUG);
    esp_log_level_set("sensor_service", ESP_LOG_DEBUG);
}

}  // namespace logging
