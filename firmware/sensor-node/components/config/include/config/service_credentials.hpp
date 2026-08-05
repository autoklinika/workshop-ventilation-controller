#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "esp_err.h"
#include "nvs.h"

namespace config {

inline constexpr std::size_t kWifiSsidMaximumBytes = 32;
inline constexpr std::size_t kWifiPskMaximumBytes = 63;
inline constexpr std::size_t kServiceNodeIdMaximumBytes = 32;
inline constexpr std::size_t kServiceKeyIdMaximumBytes = 32;
inline constexpr std::size_t kServiceAuthenticationKeyBytes = 32;

struct ServiceCredentials {
    std::array<char, kWifiSsidMaximumBytes + 1> wifi_ssid{};
    std::array<char, kWifiPskMaximumBytes + 1> wifi_psk{};
    std::array<char, kServiceNodeIdMaximumBytes + 1> node_id{};
    std::array<char, kServiceKeyIdMaximumBytes + 1> key_id{};
    std::array<std::uint8_t, kServiceAuthenticationKeyBytes> authentication_key{};
};

// The service channel is optional. ESP_ERR_NVS_NOT_FOUND means that the node
// has no local service credentials and must continue production operation on
// SEN55 + Modbus RTU without starting Wi-Fi.
esp_err_t load_service_credentials(ServiceCredentials& credentials);

}  // namespace config
