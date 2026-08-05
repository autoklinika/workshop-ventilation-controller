#include "config/service_credentials.hpp"

#include <array>
#include <cctype>
#include <cstring>

#include "nvs.h"
#include "nvs_flash.h"

namespace config {
namespace {
constexpr char kNamespace[] = "service_cfg";
constexpr char kWifiSsidKey[] = "wifi_ssid";
constexpr char kWifiPskKey[] = "wifi_psk";
constexpr char kNodeIdKey[] = "node_id";
constexpr char kKeyIdKey[] = "key_id";
constexpr char kAuthenticationKey[] = "auth_key";

bool valid_node_id(const char* value)
{
    const std::size_t length = std::strlen(value);
    if (length == 0 || length > kServiceNodeIdMaximumBytes) {
        return false;
    }
    for (std::size_t index = 0; index < length; ++index) {
        const unsigned char character = static_cast<unsigned char>(value[index]);
        const bool valid = std::islower(character) || std::isdigit(character) || character == '-';
        if (!valid || (index == 0 && character == '-')) {
            return false;
        }
    }
    return true;
}

bool valid_key_id(const char* value)
{
    const std::size_t length = std::strlen(value);
    if (length == 0 || length > kServiceKeyIdMaximumBytes) {
        return false;
    }
    for (std::size_t index = 0; index < length; ++index) {
        const unsigned char character = static_cast<unsigned char>(value[index]);
        if (!(std::isalnum(character) || character == '.' || character == '_' || character == '-')) {
            return false;
        }
    }
    return true;
}

template <std::size_t N>
esp_err_t read_string(const nvs_handle_t handle,
                      const char* key,
                      std::array<char, N>& destination)
{
    std::size_t required = destination.size();
    const esp_err_t result = nvs_get_str(handle, key, destination.data(), &required);
    if (result != ESP_OK) {
        return result;
    }
    if (required == 0 || required > destination.size()) {
        return ESP_ERR_INVALID_SIZE;
    }
    destination.back() = '\0';
    return ESP_OK;
}

bool printable_ascii(const char* value)
{
    for (const unsigned char* current = reinterpret_cast<const unsigned char*>(value);
         *current != '\0';
         ++current) {
        if (*current < 32 || *current > 126) {
            return false;
        }
    }
    return true;
}
}  // namespace

esp_err_t load_service_credentials(ServiceCredentials& credentials)
{
    credentials = {};

    const esp_err_t init_result = nvs_flash_init();
    if (init_result != ESP_OK) {
        return init_result;
    }

    nvs_handle_t handle{};
    esp_err_t result = nvs_open(kNamespace, NVS_READONLY, &handle);
    if (result != ESP_OK) {
        return result;
    }

    result = read_string(handle, kWifiSsidKey, credentials.wifi_ssid);
    if (result == ESP_OK) {
        result = read_string(handle, kWifiPskKey, credentials.wifi_psk);
    }
    if (result == ESP_OK) {
        result = read_string(handle, kNodeIdKey, credentials.node_id);
    }
    if (result == ESP_OK) {
        result = read_string(handle, kKeyIdKey, credentials.key_id);
    }
    if (result == ESP_OK) {
        std::size_t key_size = credentials.authentication_key.size();
        result = nvs_get_blob(handle,
                              kAuthenticationKey,
                              credentials.authentication_key.data(),
                              &key_size);
        if (result == ESP_OK && key_size != credentials.authentication_key.size()) {
            result = ESP_ERR_INVALID_SIZE;
        }
    }
    nvs_close(handle);

    if (result != ESP_OK) {
        credentials = {};
        return result;
    }

    const std::size_t ssid_length = std::strlen(credentials.wifi_ssid.data());
    const std::size_t psk_length = std::strlen(credentials.wifi_psk.data());
    if (ssid_length == 0 || ssid_length > kWifiSsidMaximumBytes ||
        psk_length < 16 || psk_length > kWifiPskMaximumBytes ||
        !printable_ascii(credentials.wifi_psk.data()) ||
        !valid_node_id(credentials.node_id.data()) ||
        !valid_key_id(credentials.key_id.data())) {
        credentials = {};
        return ESP_ERR_INVALID_ARG;
    }

    return ESP_OK;
}

}  // namespace config
