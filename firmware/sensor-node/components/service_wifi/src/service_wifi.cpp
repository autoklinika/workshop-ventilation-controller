#include "service_wifi/service_wifi.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <limits>

#include "config/firmware_config.hpp"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "logging/log.hpp"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "psa/crypto.h"

namespace service_wifi {
namespace {
constexpr char kTag[] = "service_wifi";
constexpr char kProtocol[] = "WVC-HB1";
constexpr char kReceiverAddress[] = "10.55.0.1";
constexpr std::uint16_t kReceiverPort = 45'551;
constexpr std::uint32_t kHeartbeatPeriodMs = 10'000;
constexpr std::uint32_t kMaximumBackoffMs = 60'000;
constexpr std::uint32_t kInitialBackoffMs = 1'000;
constexpr EventBits_t kGotIpBit = BIT0;
constexpr EventBits_t kDisconnectedBit = BIT1;
constexpr std::size_t kPayloadCapacity = 1'400;
constexpr std::size_t kPacketCapacity = kPayloadCapacity + 1 + 64;
constexpr std::uint32_t kTaskStackBytes = 8'192;
constexpr UBaseType_t kTaskPriority = 2;
constexpr BaseType_t kTaskCore = 1;

const char* bool_json(const bool value)
{
    return value ? "true" : "false";
}

void bytes_to_hex(const std::uint8_t* bytes,
                  const std::size_t length,
                  char* output)
{
    constexpr char kHex[] = "0123456789abcdef";
    for (std::size_t index = 0; index < length; ++index) {
        output[index * 2] = kHex[bytes[index] >> 4U];
        output[index * 2 + 1] = kHex[bytes[index] & 0x0FU];
    }
    output[length * 2] = '\0';
}

esp_err_t calculate_hmac(const std::array<std::uint8_t, 32>& key,
                         const std::uint8_t* message,
                         const std::size_t message_length,
                         std::array<std::uint8_t, 32>& output)
{
    const psa_status_t init_status = psa_crypto_init();
    if (init_status != PSA_SUCCESS) {
        return ESP_FAIL;
    }

    psa_key_attributes_t attributes = PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_usage_flags(&attributes, PSA_KEY_USAGE_SIGN_MESSAGE);
    psa_set_key_algorithm(&attributes, PSA_ALG_HMAC(PSA_ALG_SHA_256));
    psa_set_key_type(&attributes, PSA_KEY_TYPE_HMAC);
    psa_set_key_bits(&attributes, key.size() * 8U);

    psa_key_id_t key_id{};
    psa_status_t status = psa_import_key(&attributes,
                                         key.data(),
                                         key.size(),
                                         &key_id);
    psa_reset_key_attributes(&attributes);
    if (status != PSA_SUCCESS) {
        return ESP_FAIL;
    }

    std::size_t output_length{};
    status = psa_mac_compute(key_id,
                             PSA_ALG_HMAC(PSA_ALG_SHA_256),
                             message,
                             message_length,
                             output.data(),
                             output.size(),
                             &output_length);
    static_cast<void>(psa_destroy_key(key_id));
    return status == PSA_SUCCESS && output_length == output.size() ? ESP_OK : ESP_FAIL;
}
}  // namespace

esp_err_t ServiceWifi::start(const config::ServiceCredentials& credentials)
{
    if (started_) {
        return ESP_ERR_INVALID_STATE;
    }
    credentials_ = credentials;
    boot_id_ = (static_cast<std::uint64_t>(esp_random()) << 32U) | esp_random();

    EventGroupHandle_t group = xEventGroupCreate();
    if (group == nullptr) {
        return ESP_ERR_NO_MEM;
    }
    event_group_ = group;

    TaskHandle_t task{};
    const BaseType_t created = xTaskCreatePinnedToCore(
        &ServiceWifi::task_entry,
        "wvc_service_wifi",
        kTaskStackBytes,
        this,
        kTaskPriority,
        &task,
        kTaskCore);
    if (created != pdPASS) {
        vEventGroupDelete(group);
        event_group_ = nullptr;
        credentials_ = {};
        return ESP_ERR_NO_MEM;
    }

    task_ = task;
    started_ = true;
    LOG_INFO(kTag,
             "optional service task started node_id=%s target=%s:%u; RS-485 remains production channel",
             credentials_.node_id.data(),
             kReceiverAddress,
             static_cast<unsigned>(kReceiverPort));
    return ESP_OK;
}

void ServiceWifi::update_snapshot(const HeartbeatSnapshot& snapshot)
{
    portENTER_CRITICAL(&snapshot_lock_);
    snapshot_ = snapshot;
    portEXIT_CRITICAL(&snapshot_lock_);
}

bool ServiceWifi::started() const
{
    return started_;
}

void ServiceWifi::task_entry(void* context)
{
    static_cast<ServiceWifi*>(context)->run();
}

void ServiceWifi::event_handler(void* context,
                                const char* event_base,
                                const std::int32_t event_id,
                                void*)
{
    auto* self = static_cast<ServiceWifi*>(context);
    auto* group = static_cast<EventGroupHandle_t>(self->event_group_);
    if (group == nullptr) {
        return;
    }

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(group, kGotIpBit);
        xEventGroupSetBits(group, kDisconnectedBit);
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        xEventGroupClearBits(group, kDisconnectedBit);
        xEventGroupSetBits(group, kGotIpBit);
    }
}

void ServiceWifi::run()
{
    const esp_err_t init_result = initialize_wifi();
    if (init_result != ESP_OK) {
        LOG_WARN(kTag,
                 "service Wi-Fi initialization failed: %s; SEN55 and Modbus continue",
                 esp_err_to_name(init_result));
        vTaskDelete(nullptr);
    }

    auto* group = static_cast<EventGroupHandle_t>(event_group_);
    std::uint32_t backoff_ms = kInitialBackoffMs;
    std::int64_t next_heartbeat_us = 0;

    while (true) {
        EventBits_t bits = xEventGroupGetBits(group);
        if ((bits & kGotIpBit) == 0) {
            xEventGroupClearBits(group, kDisconnectedBit);
            const esp_err_t connect_result = esp_wifi_connect();
            if (connect_result != ESP_OK && connect_result != ESP_ERR_WIFI_CONN) {
                LOG_WARN(kTag, "Wi-Fi connect request failed: %s", esp_err_to_name(connect_result));
            }

            bits = xEventGroupWaitBits(group,
                                       kGotIpBit,
                                       pdFALSE,
                                       pdTRUE,
                                       pdMS_TO_TICKS(backoff_ms));
            if ((bits & kGotIpBit) == 0) {
                const std::uint32_t jitter_ms = esp_random() % 501U;
                vTaskDelay(pdMS_TO_TICKS(backoff_ms + jitter_ms));
                backoff_ms = std::min(backoff_ms * 2U, kMaximumBackoffMs);
                continue;
            }

            backoff_ms = kInitialBackoffMs;
            next_heartbeat_us = esp_timer_get_time() +
                                static_cast<std::int64_t>(esp_random() % 2'001U) * 1'000;
            LOG_INFO(kTag, "service Wi-Fi obtained a private DHCP address");
        }

        const std::int64_t now_us = esp_timer_get_time();
        if (now_us >= next_heartbeat_us) {
            const esp_err_t send_result = send_heartbeat();
            if (send_result != ESP_OK) {
                LOG_WARN(kTag,
                         "heartbeat send failed: %s; production channel unaffected",
                         esp_err_to_name(send_result));
            }
            next_heartbeat_us = now_us + static_cast<std::int64_t>(kHeartbeatPeriodMs) * 1'000;
        }

        static_cast<void>(xEventGroupWaitBits(group,
                                              kDisconnectedBit,
                                              pdTRUE,
                                              pdFALSE,
                                              pdMS_TO_TICKS(250)));
    }
}

esp_err_t ServiceWifi::initialize_wifi()
{
    esp_err_t result = esp_netif_init();
    if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
        return result;
    }
    result = esp_event_loop_create_default();
    if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
        return result;
    }

    wifi_init_config_t wifi_init = WIFI_INIT_CONFIG_DEFAULT();
    result = esp_wifi_init(&wifi_init);
    if (result != ESP_OK) {
        return result;
    }

    esp_netif_inherent_config_t inherent = ESP_NETIF_INHERENT_DEFAULT_WIFI_STA();
    esp_netif_config_t netif_config = {
        .base = &inherent,
        .stack = ESP_NETIF_NETSTACK_DEFAULT_WIFI_STA,
    };
    esp_netif_t* netif = esp_netif_new(&netif_config);
    if (netif == nullptr) {
        return ESP_ERR_NO_MEM;
    }
    netif_ = netif;

    result = esp_netif_attach_wifi_station(netif);
    if (result != ESP_OK) {
        return result;
    }
    result = esp_wifi_set_default_wifi_sta_handlers();
    if (result != ESP_OK) {
        return result;
    }

    esp_event_handler_instance_t wifi_instance{};
    result = esp_event_handler_instance_register(WIFI_EVENT,
                                                 ESP_EVENT_ANY_ID,
                                                 &ServiceWifi::event_handler,
                                                 this,
                                                 &wifi_instance);
    if (result != ESP_OK) {
        return result;
    }
    wifi_event_instance_ = wifi_instance;

    esp_event_handler_instance_t ip_instance{};
    result = esp_event_handler_instance_register(IP_EVENT,
                                                 IP_EVENT_STA_GOT_IP,
                                                 &ServiceWifi::event_handler,
                                                 this,
                                                 &ip_instance);
    if (result != ESP_OK) {
        return result;
    }
    ip_event_instance_ = ip_instance;

    wifi_config_t wifi_config{};
    std::memcpy(wifi_config.sta.ssid,
                credentials_.wifi_ssid.data(),
                std::strlen(credentials_.wifi_ssid.data()));
    std::memcpy(wifi_config.sta.password,
                credentials_.wifi_psk.data(),
                std::strlen(credentials_.wifi_psk.data()));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    wifi_config.sta.pmf_cfg.capable = true;
    wifi_config.sta.pmf_cfg.required = false;

    result = esp_wifi_set_mode(WIFI_MODE_STA);
    if (result != ESP_OK) {
        return result;
    }
    result = esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
    if (result != ESP_OK) {
        return result;
    }
    result = esp_wifi_set_ps(WIFI_PS_NONE);
    if (result != ESP_OK) {
        return result;
    }
    return esp_wifi_start();
}

esp_err_t ServiceWifi::send_heartbeat()
{
    HeartbeatSnapshot snapshot{};
    portENTER_CRITICAL(&snapshot_lock_);
    snapshot = snapshot_;
    portEXIT_CRITICAL(&snapshot_lock_);

    const std::int64_t now_us = esp_timer_get_time();
    wifi_ap_record_t access_point{};
    std::int32_t rssi = -127;
    if (esp_wifi_sta_get_ap_info(&access_point) == ESP_OK) {
        rssi = access_point.rssi;
    }

    std::array<std::uint8_t, 6> mac{};
    const esp_err_t mac_result = esp_wifi_get_mac(WIFI_IF_STA, mac.data());
    if (mac_result != ESP_OK) {
        return mac_result;
    }
    char mac_text[18]{};
    std::snprintf(mac_text,
                  sizeof(mac_text),
                  "%02X:%02X:%02X:%02X:%02X:%02X",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    const esp_partition_t* partition = esp_ota_get_running_partition();
    const char* partition_label = partition != nullptr ? partition->label : "unknown";
    bool ota_pending = false;
    if (partition != nullptr) {
        esp_ota_img_states_t state{};
        ota_pending = esp_ota_get_state_partition(partition, &state) == ESP_OK &&
                      state == ESP_OTA_IMG_PENDING_VERIFY;
    }

    const std::uint32_t last_60_seconds = requests_last_60_seconds(
        snapshot.modbus_requests_total);
    const std::uint32_t uptime_s = static_cast<std::uint32_t>(
        static_cast<std::uint64_t>(now_us) / 1'000'000U);

    char boot_id_text[17]{};
    std::snprintf(boot_id_text,
                  sizeof(boot_id_text),
                  "%016llx",
                  static_cast<unsigned long long>(boot_id_));

    std::array<char, kPayloadCapacity> payload{};
    const int payload_length = std::snprintf(
        payload.data(),
        payload.size(),
        "{\"boot_id\":\"%s\",\"firmware\":\"%s\",\"key_id\":\"%s\","
        "\"last_modbus_request_age_ms\":%ld,\"mac\":\"%s\","
        "\"measurement_age_ms\":%ld,\"modbus_monitor_ready\":%s,"
        "\"modbus_requests_last_60s\":%lu,\"modbus_requests_total\":%lu,"
        "\"modbus_service_errors\":%lu,\"modbus_slave\":%u,"
        "\"node_id\":\"%s\",\"ota_partition\":\"%s\",\"ota_pending\":%s,"
        "\"protocol\":\"%s\",\"reset_reason\":%d,\"rs485_ready\":%s,"
        "\"schema\":1,\"sensor_communication_failures\":%lu,"
        "\"sensor_crc_failures\":%lu,\"sensor_detection_failures\":%lu,"
        "\"sensor_last_error\":%ld,\"sensor_state\":\"%s\","
        "\"sensor_successful_measurements\":%lu,\"seq\":%llu,"
        "\"uptime_s\":%lu,\"wifi_rssi_dbm\":%ld}",
        boot_id_text,
        config::firmware::kVersion,
        credentials_.key_id.data(),
        static_cast<long>(age_ms(now_us, snapshot.last_modbus_request_us)),
        mac_text,
        static_cast<long>(age_ms(now_us, snapshot.last_measurement_success_us)),
        bool_json(snapshot.modbus_monitor_ready),
        static_cast<unsigned long>(last_60_seconds),
        static_cast<unsigned long>(snapshot.modbus_requests_total),
        static_cast<unsigned long>(snapshot.modbus_service_errors),
        static_cast<unsigned>(snapshot.modbus_slave),
        credentials_.node_id.data(),
        partition_label,
        bool_json(ota_pending),
        kProtocol,
        static_cast<int>(esp_reset_reason()),
        bool_json(snapshot.rs485_ready),
        static_cast<unsigned long>(snapshot.sensor_communication_failures),
        static_cast<unsigned long>(snapshot.sensor_crc_failures),
        static_cast<unsigned long>(snapshot.sensor_detection_failures),
        static_cast<long>(snapshot.sensor_last_error),
        snapshot.sensor_state.data(),
        static_cast<unsigned long>(snapshot.sensor_successful_measurements),
        static_cast<unsigned long long>(sequence_),
        static_cast<unsigned long>(uptime_s),
        static_cast<long>(rssi));
    if (payload_length <= 0 || static_cast<std::size_t>(payload_length) >= payload.size()) {
        return ESP_ERR_INVALID_SIZE;
    }

    std::array<std::uint8_t, 32> signature{};
    const esp_err_t hmac_result = calculate_hmac(
        credentials_.authentication_key,
        reinterpret_cast<const std::uint8_t*>(payload.data()),
        static_cast<std::size_t>(payload_length),
        signature);
    if (hmac_result != ESP_OK) {
        return hmac_result;
    }

    char signature_hex[65]{};
    bytes_to_hex(signature.data(), signature.size(), signature_hex);
    std::array<char, kPacketCapacity> packet{};
    const int packet_length = std::snprintf(packet.data(),
                                            packet.size(),
                                            "%.*s\n%s",
                                            payload_length,
                                            payload.data(),
                                            signature_hex);
    if (packet_length <= 0 || static_cast<std::size_t>(packet_length) >= packet.size()) {
        return ESP_ERR_INVALID_SIZE;
    }

    sockaddr_in destination{};
    destination.sin_family = AF_INET;
    destination.sin_port = htons(kReceiverPort);
    if (inet_pton(AF_INET, kReceiverAddress, &destination.sin_addr) != 1) {
        return ESP_ERR_INVALID_ARG;
    }

    const int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (socket_fd < 0) {
        return ESP_FAIL;
    }
    const int sent = sendto(socket_fd,
                            packet.data(),
                            static_cast<std::size_t>(packet_length),
                            0,
                            reinterpret_cast<const sockaddr*>(&destination),
                            sizeof(destination));
    const int saved_errno = errno;
    close(socket_fd);
    if (sent != packet_length) {
        errno = saved_errno;
        return ESP_FAIL;
    }

    ++sequence_;
    return ESP_OK;
}

std::uint32_t ServiceWifi::requests_last_60_seconds(const std::uint32_t current_total)
{
    std::uint32_t result = 0;
    if (request_history_count_ == 0) {
        request_history_[0] = current_total;
        request_history_count_ = 1;
        request_history_index_ = 1;
        return 0;
    }

    if (request_history_count_ < request_history_.size()) {
        result = current_total - request_history_[0];
        request_history_[request_history_index_] = current_total;
        ++request_history_count_;
        request_history_index_ = (request_history_index_ + 1) % request_history_.size();
        return result;
    }

    result = current_total - request_history_[request_history_index_];
    request_history_[request_history_index_] = current_total;
    request_history_index_ = (request_history_index_ + 1) % request_history_.size();
    return result;
}

std::int32_t ServiceWifi::age_ms(const std::int64_t now_us,
                                 const std::int64_t event_us)
{
    if (event_us <= 0 || event_us > now_us) {
        return -1;
    }
    const std::int64_t milliseconds = (now_us - event_us) / 1'000;
    return static_cast<std::int32_t>(std::min<std::int64_t>(
        milliseconds,
        std::numeric_limits<std::int32_t>::max()));
}

}  // namespace service_wifi
