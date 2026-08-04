#include "config/modbus_address.hpp"

#include "nvs.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

namespace config {
namespace {
constexpr char kNamespace[] = "device_config";
constexpr char kAddressKey[] = "modbus_addr";

static_assert(valid_modbus_slave_address(
    CONFIG_WVC_MODBUS_SLAVE_ADDRESS_DEFAULT));
}  // namespace

esp_err_t load_modbus_slave_address(std::uint8_t& address)
{
    address = static_cast<std::uint8_t>(
        CONFIG_WVC_MODBUS_SLAVE_ADDRESS_DEFAULT);

    const esp_err_t init_result = nvs_flash_init();
    if (init_result != ESP_OK) {
        return init_result;
    }

    nvs_handle_t handle{};
    esp_err_t result = nvs_open(kNamespace, NVS_READONLY, &handle);
    if (result == ESP_ERR_NVS_NOT_FOUND) {
        return ESP_OK;
    }
    if (result != ESP_OK) {
        return result;
    }

    std::uint8_t provisioned_address{};
    result = nvs_get_u8(handle, kAddressKey, &provisioned_address);
    nvs_close(handle);

    if (result == ESP_ERR_NVS_NOT_FOUND) {
        return ESP_OK;
    }
    if (result != ESP_OK) {
        return result;
    }
    if (!valid_modbus_slave_address(provisioned_address)) {
        return ESP_ERR_INVALID_ARG;
    }

    address = provisioned_address;
    return ESP_OK;
}

}  // namespace config
