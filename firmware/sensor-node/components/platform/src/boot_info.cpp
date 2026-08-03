#include "platform/boot_info.hpp"

#include "config/firmware_config.hpp"
#include "esp_app_desc.h"
#include "esp_idf_version.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "logging/log.hpp"

namespace platform {
namespace {
constexpr char kTag[] = "platform";
}

void BootInfo::log()
{
    const esp_app_desc_t* app = esp_app_get_description();
    const esp_partition_t* running = esp_ota_get_running_partition();

    LOG_INFO(kTag,
             "project=%s firmware=%s idf=%s build=%s %s",
             config::firmware::kProjectName,
             config::firmware::kVersion,
             esp_get_idf_version(),
             app != nullptr ? app->date : "unknown",
             app != nullptr ? app->time : "unknown");
    LOG_INFO(kTag,
             "reset_reason=%d running_partition=%s offset=0x%08lX size=%lu",
             static_cast<int>(esp_reset_reason()),
             running != nullptr ? running->label : "unknown",
             running != nullptr ? static_cast<unsigned long>(running->address) : 0UL,
             running != nullptr ? static_cast<unsigned long>(running->size) : 0UL);
}

}  // namespace platform
