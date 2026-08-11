#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "config/service_credentials.hpp"
#include "esp_err.h"
#include "esp_http_server.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"

namespace service_ota {

class ServiceOta final {
public:
    enum class State : std::uint8_t {
        kIdle,
        kReceiving,
        kRebootPending,
        kError,
    };

    ServiceOta() = default;

    ServiceOta(const ServiceOta&) = delete;
    ServiceOta& operator=(const ServiceOta&) = delete;

    esp_err_t start(const config::ServiceCredentials& credentials);
    [[nodiscard]] bool started() const;

private:
    struct Status {
        State state{State::kIdle};
        std::uint32_t bytes_written{0};
        std::uint32_t expected_bytes{0};
        std::array<char, 65> image_sha256{};
        std::array<char, 17> target_partition{};
        std::array<char, 96> last_error{};
    };

    static esp_err_t challenge_handler(httpd_req_t* request);
    static esp_err_t status_handler(httpd_req_t* request);
    static esp_err_t image_handler(httpd_req_t* request);
    static void restart_task(void* context);

    esp_err_t handle_challenge(httpd_req_t* request);
    esp_err_t handle_status(httpd_req_t* request);
    esp_err_t handle_image(httpd_req_t* request);
    esp_err_t start_server();

    bool consume_challenge(const char* boot_id, const char* nonce);
    void generate_challenge();
    void set_receiving(std::uint32_t expected_bytes, const char* image_sha256);
    void set_progress(std::uint32_t bytes_written);
    void set_success(const char* target_partition);
    void set_error(const char* message);
    [[nodiscard]] Status status_snapshot() const;

    config::ServiceCredentials credentials_{};
    httpd_handle_t server_{nullptr};
    mutable portMUX_TYPE state_lock_ = portMUX_INITIALIZER_UNLOCKED;
    Status status_{};
    std::uint64_t boot_id_{0};
    std::array<char, 33> nonce_{};
    std::int64_t nonce_expires_us_{0};
    bool challenge_available_{false};
    bool started_{false};
};

}  // namespace service_ota
