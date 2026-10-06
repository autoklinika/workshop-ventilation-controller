#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "config/service_credentials.hpp"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"

namespace service_wifi {

struct HeartbeatSnapshot {
    std::array<char, 32> sensor_state{};
    std::int64_t last_measurement_success_us{0};
    std::int32_t sensor_last_error{0};
    std::uint32_t sensor_detection_failures{0};
    std::uint32_t sensor_communication_failures{0};
    std::uint32_t sensor_crc_failures{0};
    std::uint32_t sensor_successful_measurements{0};
    bool rs485_ready{false};
    std::uint8_t modbus_slave{0};
    bool modbus_monitor_ready{false};
    std::uint32_t modbus_requests_total{0};
    std::int64_t last_modbus_request_us{0};
    std::uint32_t modbus_service_errors{0};
};

class ServiceWifi final {
public:
    ServiceWifi() = default;

    ServiceWifi(const ServiceWifi&) = delete;
    ServiceWifi& operator=(const ServiceWifi&) = delete;

    esp_err_t start(const config::ServiceCredentials& credentials);
    void update_snapshot(const HeartbeatSnapshot& snapshot);

    [[nodiscard]] bool started() const;

private:
    struct TransportDiagnostics {
        std::uint32_t wifi_disconnect_events{0};
        std::uint32_t wifi_got_ip_events{0};
        std::uint32_t heartbeat_send_attempts{0};
        std::uint32_t heartbeat_send_successes{0};
        std::uint32_t heartbeat_send_failures{0};
        std::uint32_t heartbeat_consecutive_send_failures{0};
        std::uint32_t heartbeat_max_consecutive_send_failures{0};
        std::int32_t heartbeat_last_send_error{ESP_OK};
        std::uint32_t wifi_last_disconnect_reason{0};
    };

    static void task_entry(void* context);
    static void event_handler(void* context,
                              const char* event_base,
                              std::int32_t event_id,
                              void* event_data);

    void run();
    esp_err_t initialize_wifi();
    esp_err_t send_heartbeat();
    void record_send_attempt();
    void record_send_result(esp_err_t result);
    [[nodiscard]] TransportDiagnostics transport_diagnostics() const;
    std::uint32_t requests_last_60_seconds(std::uint32_t current_total);
    static std::int32_t age_ms(std::int64_t now_us, std::int64_t event_us);

    config::ServiceCredentials credentials_{};
    mutable portMUX_TYPE snapshot_lock_ = portMUX_INITIALIZER_UNLOCKED;
    HeartbeatSnapshot snapshot_{};
    mutable portMUX_TYPE transport_lock_ = portMUX_INITIALIZER_UNLOCKED;
    TransportDiagnostics transport_diagnostics_{};
    void* event_group_{nullptr};
    void* task_{nullptr};
    void* netif_{nullptr};
    void* wifi_event_instance_{nullptr};
    void* ip_event_instance_{nullptr};
    std::uint64_t boot_id_{0};
    std::uint64_t sequence_{0};
    std::array<std::uint32_t, 6> request_history_{};
    std::size_t request_history_count_{0};
    std::size_t request_history_index_{0};
    bool started_{false};
};

}  // namespace service_wifi
