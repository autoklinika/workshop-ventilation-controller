#include "service_ota/service_ota.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <new>

#include "config/firmware_config.hpp"
#include "esp_ota_ops.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/task.h"
#include "logging/log.hpp"
#include "mbedtls/sha256.h"
#include "psa/crypto.h"

namespace service_ota {
namespace {
constexpr char kTag[] = "service_ota";
constexpr char kProtocol[] = "WVC-OTA1";
constexpr std::uint16_t kServerPort = 45'552;
constexpr std::int64_t kChallengeLifetimeUs = 30'000'000;
constexpr std::size_t kNonceBytes = 16;
constexpr std::size_t kDigestBytes = 32;
constexpr std::size_t kHeaderCapacity = 128;
constexpr std::size_t kReceiveBufferBytes = 4'096;
constexpr std::size_t kCanonicalCapacity = 512;
constexpr std::size_t kServerTaskStackBytes = 16'384;
constexpr std::uint32_t kRestartDelayMs = 3'000;
constexpr int kMaximumReceiveTimeouts = 3;

const char* state_name(const ServiceOta::State state)
{
    switch (state) {
    case ServiceOta::State::kIdle:
        return "idle";
    case ServiceOta::State::kReceiving:
        return "receiving";
    case ServiceOta::State::kRebootPending:
        return "reboot_pending";
    case ServiceOta::State::kError:
        return "error";
    }
    return "unknown";
}

const char* ota_image_state_name(const esp_ota_img_states_t state)
{
    switch (state) {
    case ESP_OTA_IMG_NEW:
        return "new";
    case ESP_OTA_IMG_PENDING_VERIFY:
        return "pending_verify";
    case ESP_OTA_IMG_VALID:
        return "valid";
    case ESP_OTA_IMG_INVALID:
        return "invalid";
    case ESP_OTA_IMG_ABORTED:
        return "aborted";
    case ESP_OTA_IMG_UNDEFINED:
        return "undefined";
    }
    return "unknown";
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

bool hex_digit(const char value, std::uint8_t& output)
{
    if (value >= '0' && value <= '9') {
        output = static_cast<std::uint8_t>(value - '0');
        return true;
    }
    if (value >= 'a' && value <= 'f') {
        output = static_cast<std::uint8_t>(value - 'a' + 10);
        return true;
    }
    if (value >= 'A' && value <= 'F') {
        output = static_cast<std::uint8_t>(value - 'A' + 10);
        return true;
    }
    return false;
}

bool hex_to_bytes(const char* text,
                  const std::size_t text_length,
                  std::uint8_t* output,
                  const std::size_t output_length)
{
    if (text_length != output_length * 2) {
        return false;
    }
    for (std::size_t index = 0; index < output_length; ++index) {
        std::uint8_t high{};
        std::uint8_t low{};
        if (!hex_digit(text[index * 2], high) ||
            !hex_digit(text[index * 2 + 1], low)) {
            return false;
        }
        output[index] = static_cast<std::uint8_t>((high << 4U) | low);
    }
    return true;
}

bool constant_time_equal(const std::uint8_t* left,
                         const std::uint8_t* right,
                         const std::size_t length)
{
    std::uint8_t difference = 0;
    for (std::size_t index = 0; index < length; ++index) {
        difference = static_cast<std::uint8_t>(difference | (left[index] ^ right[index]));
    }
    return difference == 0;
}

esp_err_t calculate_hmac(const std::array<std::uint8_t, 32>& key,
                         const std::uint8_t* message,
                         const std::size_t message_length,
                         std::array<std::uint8_t, kDigestBytes>& output)
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

esp_err_t send_json(httpd_req_t* request,
                    const char* status,
                    const char* body)
{
    static_cast<void>(httpd_resp_set_status(request, status));
    static_cast<void>(httpd_resp_set_type(request, "application/json"));
    static_cast<void>(httpd_resp_set_hdr(request, "Cache-Control", "no-store"));
    return httpd_resp_send(request, body, HTTPD_RESP_USE_STRLEN);
}

esp_err_t send_error(httpd_req_t* request,
                     const char* status,
                     const char* error)
{
    std::array<char, 192> body{};
    const int length = std::snprintf(body.data(),
                                     body.size(),
                                     "{\"ok\":false,\"error\":\"%s\"}",
                                     error);
    if (length <= 0 || static_cast<std::size_t>(length) >= body.size()) {
        return send_json(request,
                         "500 Internal Server Error",
                         "{\"ok\":false,\"error\":\"internal error\"}");
    }
    return send_json(request, status, body.data());
}

bool read_header(httpd_req_t* request,
                 const char* name,
                 char* output,
                 const std::size_t capacity)
{
    const std::size_t length = httpd_req_get_hdr_value_len(request, name);
    if (length == 0 || length >= capacity) {
        return false;
    }
    return httpd_req_get_hdr_value_str(request, name, output, capacity) == ESP_OK;
}

bool parse_size(const char* text, std::uint32_t& output)
{
    errno = 0;
    char* end{};
    const unsigned long long value = std::strtoull(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' ||
        value == 0 || value > std::numeric_limits<std::uint32_t>::max()) {
        return false;
    }
    output = static_cast<std::uint32_t>(value);
    return true;
}

unsigned stack_high_watermark()
{
    return static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr));
}
}  // namespace

esp_err_t ServiceOta::start(const config::ServiceCredentials& credentials)
{
    if (started_) {
        return ESP_ERR_INVALID_STATE;
    }
    credentials_ = credentials;
    boot_id_ = (static_cast<std::uint64_t>(esp_random()) << 32U) | esp_random();
    const esp_err_t result = start_server();
    if (result != ESP_OK) {
        credentials_ = {};
        return result;
    }
    started_ = true;
    LOG_INFO(kTag,
             "manual authenticated OTA server started node_id=%s port=%u stack=%u; RS-485 remains production channel",
             credentials_.node_id.data(),
             static_cast<unsigned>(kServerPort),
             static_cast<unsigned>(kServerTaskStackBytes));
    return ESP_OK;
}

bool ServiceOta::started() const
{
    return started_;
}

esp_err_t ServiceOta::start_server()
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = kServerPort;
    config.max_uri_handlers = 3;
    config.recv_wait_timeout = 15;
    config.send_wait_timeout = 15;
    config.lru_purge_enable = true;
    config.stack_size = kServerTaskStackBytes;

    esp_err_t result = httpd_start(&server_, &config);
    if (result != ESP_OK) {
        return result;
    }

    httpd_uri_t challenge{};
    challenge.uri = "/v1/ota/challenge";
    challenge.method = HTTP_GET;
    challenge.handler = &ServiceOta::challenge_handler;
    challenge.user_ctx = this;
    result = httpd_register_uri_handler(server_, &challenge);
    if (result != ESP_OK) {
        static_cast<void>(httpd_stop(server_));
        server_ = nullptr;
        return result;
    }

    httpd_uri_t status{};
    status.uri = "/v1/ota/status";
    status.method = HTTP_GET;
    status.handler = &ServiceOta::status_handler;
    status.user_ctx = this;
    result = httpd_register_uri_handler(server_, &status);
    if (result != ESP_OK) {
        static_cast<void>(httpd_stop(server_));
        server_ = nullptr;
        return result;
    }

    httpd_uri_t image{};
    image.uri = "/v1/ota/image";
    image.method = HTTP_POST;
    image.handler = &ServiceOta::image_handler;
    image.user_ctx = this;
    result = httpd_register_uri_handler(server_, &image);
    if (result != ESP_OK) {
        static_cast<void>(httpd_stop(server_));
        server_ = nullptr;
        return result;
    }
    return ESP_OK;
}

esp_err_t ServiceOta::challenge_handler(httpd_req_t* request)
{
    auto* self = static_cast<ServiceOta*>(request->user_ctx);
    return self != nullptr ? self->handle_challenge(request) : ESP_FAIL;
}

esp_err_t ServiceOta::status_handler(httpd_req_t* request)
{
    auto* self = static_cast<ServiceOta*>(request->user_ctx);
    return self != nullptr ? self->handle_status(request) : ESP_FAIL;
}

esp_err_t ServiceOta::image_handler(httpd_req_t* request)
{
    auto* self = static_cast<ServiceOta*>(request->user_ctx);
    return self != nullptr ? self->handle_image(request) : ESP_FAIL;
}

void ServiceOta::generate_challenge()
{
    std::array<std::uint8_t, kNonceBytes> random_bytes{};
    esp_fill_random(random_bytes.data(), random_bytes.size());
    portENTER_CRITICAL(&state_lock_);
    bytes_to_hex(random_bytes.data(), random_bytes.size(), nonce_.data());
    nonce_expires_us_ = esp_timer_get_time() + kChallengeLifetimeUs;
    challenge_available_ = true;
    portEXIT_CRITICAL(&state_lock_);
}

bool ServiceOta::consume_challenge(const char* boot_id, const char* nonce)
{
    char expected_boot_id[17]{};
    std::snprintf(expected_boot_id,
                  sizeof(expected_boot_id),
                  "%016llx",
                  static_cast<unsigned long long>(boot_id_));

    bool accepted = false;
    portENTER_CRITICAL(&state_lock_);
    const std::int64_t now_us = esp_timer_get_time();
    accepted = challenge_available_ &&
               now_us <= nonce_expires_us_ &&
               std::strcmp(expected_boot_id, boot_id) == 0 &&
               std::strcmp(nonce_.data(), nonce) == 0;
    challenge_available_ = false;
    nonce_.fill('\0');
    nonce_expires_us_ = 0;
    portEXIT_CRITICAL(&state_lock_);
    return accepted;
}

esp_err_t ServiceOta::handle_challenge(httpd_req_t* request)
{
    const Status current = status_snapshot();
    if (current.state == State::kReceiving || current.state == State::kRebootPending) {
        return send_error(request, "409 Conflict", "OTA operation already active");
    }
    generate_challenge();

    char boot_id[17]{};
    char nonce[33]{};
    portENTER_CRITICAL(&state_lock_);
    std::snprintf(boot_id,
                  sizeof(boot_id),
                  "%016llx",
                  static_cast<unsigned long long>(boot_id_));
    std::snprintf(nonce, sizeof(nonce), "%s", nonce_.data());
    portEXIT_CRITICAL(&state_lock_);

    std::array<char, 256> body{};
    const int length = std::snprintf(
        body.data(),
        body.size(),
        "{\"ok\":true,\"protocol\":\"%s\",\"node_id\":\"%s\","
        "\"boot_id\":\"%s\",\"nonce\":\"%s\",\"expires_in_s\":30}",
        kProtocol,
        credentials_.node_id.data(),
        boot_id,
        nonce);
    if (length <= 0 || static_cast<std::size_t>(length) >= body.size()) {
        return send_error(request,
                          "500 Internal Server Error",
                          "challenge serialization failed");
    }
    return send_json(request, "200 OK", body.data());
}

ServiceOta::Status ServiceOta::status_snapshot() const
{
    Status snapshot{};
    portENTER_CRITICAL(&state_lock_);
    snapshot = status_;
    portEXIT_CRITICAL(&state_lock_);
    return snapshot;
}

esp_err_t ServiceOta::handle_status(httpd_req_t* request)
{
    const esp_partition_t* running = esp_ota_get_running_partition();
    const char* partition_label = running != nullptr ? running->label : "unknown";
    esp_ota_img_states_t image_state = ESP_OTA_IMG_UNDEFINED;
    const esp_err_t state_result = running != nullptr
                                      ? esp_ota_get_state_partition(running, &image_state)
                                      : ESP_ERR_NOT_FOUND;
    const bool pending = state_result == ESP_OK &&
                         image_state == ESP_OTA_IMG_PENDING_VERIFY;
    const Status current = status_snapshot();

    std::array<char, 640> body{};
    const int length = std::snprintf(
        body.data(),
        body.size(),
        "{\"ok\":true,\"protocol\":\"%s\",\"node_id\":\"%s\","
        "\"firmware\":\"%s\",\"partition\":\"%s\",\"pending\":%s,"
        "\"image_state\":\"%s\",\"state\":\"%s\","
        "\"bytes_written\":%lu,\"expected_bytes\":%lu,"
        "\"image_sha256\":\"%s\",\"target_partition\":\"%s\","
        "\"last_error\":\"%s\"}",
        kProtocol,
        credentials_.node_id.data(),
        config::firmware::kVersion,
        partition_label,
        pending ? "true" : "false",
        state_result == ESP_OK ? ota_image_state_name(image_state) : "unavailable",
        state_name(current.state),
        static_cast<unsigned long>(current.bytes_written),
        static_cast<unsigned long>(current.expected_bytes),
        current.image_sha256.data(),
        current.target_partition.data(),
        current.last_error.data());
    if (length <= 0 || static_cast<std::size_t>(length) >= body.size()) {
        return send_error(request,
                          "500 Internal Server Error",
                          "status serialization failed");
    }
    return send_json(request, "200 OK", body.data());
}

void ServiceOta::set_receiving(const std::uint32_t expected_bytes,
                               const char* image_sha256)
{
    portENTER_CRITICAL(&state_lock_);
    status_ = {};
    status_.state = State::kReceiving;
    status_.expected_bytes = expected_bytes;
    std::snprintf(status_.image_sha256.data(),
                  status_.image_sha256.size(),
                  "%s",
                  image_sha256);
    portEXIT_CRITICAL(&state_lock_);
}

void ServiceOta::set_progress(const std::uint32_t bytes_written)
{
    portENTER_CRITICAL(&state_lock_);
    status_.bytes_written = bytes_written;
    portEXIT_CRITICAL(&state_lock_);
}

void ServiceOta::set_success(const char* target_partition)
{
    portENTER_CRITICAL(&state_lock_);
    status_.state = State::kRebootPending;
    std::snprintf(status_.target_partition.data(),
                  status_.target_partition.size(),
                  "%s",
                  target_partition);
    status_.last_error.fill('\0');
    portEXIT_CRITICAL(&state_lock_);
}

void ServiceOta::set_error(const char* message)
{
    portENTER_CRITICAL(&state_lock_);
    status_.state = State::kError;
    std::snprintf(status_.last_error.data(),
                  status_.last_error.size(),
                  "%s",
                  message);
    portEXIT_CRITICAL(&state_lock_);
    LOG_WARN(kTag, "OTA operation failed: %s", message);
}

esp_err_t ServiceOta::handle_image(httpd_req_t* request)
{
    const Status before = status_snapshot();
    if (before.state == State::kReceiving || before.state == State::kRebootPending) {
        return send_error(request, "409 Conflict", "OTA operation already active");
    }

    std::array<char, kHeaderCapacity> node_id{};
    std::array<char, kHeaderCapacity> boot_id{};
    std::array<char, kHeaderCapacity> nonce{};
    std::array<char, kHeaderCapacity> image_size_text{};
    std::array<char, kHeaderCapacity> image_sha256{};
    std::array<char, kHeaderCapacity> authorization{};
    if (!read_header(request, "X-WVC-Node-ID", node_id.data(), node_id.size()) ||
        !read_header(request, "X-WVC-Boot-ID", boot_id.data(), boot_id.size()) ||
        !read_header(request, "X-WVC-Nonce", nonce.data(), nonce.size()) ||
        !read_header(request,
                     "X-WVC-Image-Size",
                     image_size_text.data(),
                     image_size_text.size()) ||
        !read_header(request,
                     "X-WVC-Image-SHA256",
                     image_sha256.data(),
                     image_sha256.size()) ||
        !read_header(request,
                     "X-WVC-Authorization",
                     authorization.data(),
                     authorization.size())) {
        return send_error(request,
                          "400 Bad Request",
                          "required OTA headers are missing or too long");
    }

    std::uint32_t image_size{};
    if (std::strcmp(node_id.data(), credentials_.node_id.data()) != 0 ||
        !parse_size(image_size_text.data(), image_size) ||
        request->content_len != image_size ||
        std::strlen(image_sha256.data()) != 64 ||
        std::strlen(authorization.data()) != 64) {
        static_cast<void>(consume_challenge(boot_id.data(), nonce.data()));
        return send_error(request, "400 Bad Request", "OTA metadata is invalid");
    }
    if (!consume_challenge(boot_id.data(), nonce.data())) {
        return send_error(request,
                          "401 Unauthorized",
                          "OTA challenge is invalid, expired or already used");
    }

    std::array<std::uint8_t, kDigestBytes> received_authorization{};
    if (!hex_to_bytes(authorization.data(),
                      std::strlen(authorization.data()),
                      received_authorization.data(),
                      received_authorization.size())) {
        return send_error(request,
                          "401 Unauthorized",
                          "OTA authorization is not valid hexadecimal");
    }

    std::array<char, kCanonicalCapacity> canonical{};
    const int canonical_length = std::snprintf(
        canonical.data(),
        canonical.size(),
        "%s\n%s\n%s\n%s\n%lu\n%s\n",
        kProtocol,
        node_id.data(),
        boot_id.data(),
        nonce.data(),
        static_cast<unsigned long>(image_size),
        image_sha256.data());
    if (canonical_length <= 0 ||
        static_cast<std::size_t>(canonical_length) >= canonical.size()) {
        return send_error(request,
                          "400 Bad Request",
                          "OTA authorization message is too large");
    }

    std::array<std::uint8_t, kDigestBytes> expected_authorization{};
    if (calculate_hmac(credentials_.authentication_key,
                       reinterpret_cast<const std::uint8_t*>(canonical.data()),
                       static_cast<std::size_t>(canonical_length),
                       expected_authorization) != ESP_OK ||
        !constant_time_equal(received_authorization.data(),
                             expected_authorization.data(),
                             expected_authorization.size())) {
        return send_error(request,
                          "401 Unauthorized",
                          "OTA HMAC authentication failed");
    }

    const esp_partition_t* running = esp_ota_get_running_partition();
    if (running == nullptr) {
        return send_error(request,
                          "500 Internal Server Error",
                          "running partition is unavailable");
    }
    esp_ota_img_states_t running_state{};
    if (esp_ota_get_state_partition(running, &running_state) == ESP_OK &&
        running_state == ESP_OTA_IMG_PENDING_VERIFY) {
        return send_error(request,
                          "409 Conflict",
                          "current image is still pending rollback validation");
    }

    const esp_partition_t* update_partition = esp_ota_get_next_update_partition(nullptr);
    if (update_partition == nullptr || image_size > update_partition->size) {
        return send_error(request,
                          "413 Payload Too Large",
                          "OTA image does not fit the inactive partition");
    }

    auto buffer = std::unique_ptr<std::uint8_t[]>(
        new (std::nothrow) std::uint8_t[kReceiveBufferBytes]);
    if (!buffer) {
        set_error("OTA receive buffer allocation failed");
        return send_error(request,
                          "503 Service Unavailable",
                          "OTA receive buffer allocation failed");
    }

    LOG_INFO(kTag,
             "OTA begin node_id=%s image_size=%lu source=%s target=%s free_heap=%lu stack_hwm=%u",
             credentials_.node_id.data(),
             static_cast<unsigned long>(image_size),
             running->label,
             update_partition->label,
             static_cast<unsigned long>(esp_get_free_heap_size()),
             stack_high_watermark());

    esp_ota_handle_t ota_handle{};
    const esp_err_t begin_result = esp_ota_begin(update_partition,
                                                 image_size,
                                                 &ota_handle);
    if (begin_result != ESP_OK) {
        set_error(esp_err_to_name(begin_result));
        return send_error(request, "409 Conflict", "OTA partition cannot be opened");
    }

    set_receiving(image_size, image_sha256.data());
    mbedtls_sha256_context sha{};
    mbedtls_sha256_init(&sha);
    if (mbedtls_sha256_starts(&sha, 0) != 0) {
        static_cast<void>(esp_ota_abort(ota_handle));
        mbedtls_sha256_free(&sha);
        set_error("SHA-256 initialization failed");
        return send_error(request,
                          "500 Internal Server Error",
                          "SHA-256 initialization failed");
    }

    std::uint32_t bytes_written = 0;
    int timeout_count = 0;
    esp_err_t transfer_result = ESP_OK;
    while (bytes_written < image_size) {
        const std::size_t remaining = image_size - bytes_written;
        const std::size_t requested = std::min(kReceiveBufferBytes, remaining);
        const int received = httpd_req_recv(
            request,
            reinterpret_cast<char*>(buffer.get()),
            requested);
        if (received == HTTPD_SOCK_ERR_TIMEOUT) {
            ++timeout_count;
            if (timeout_count <= kMaximumReceiveTimeouts) {
                continue;
            }
            transfer_result = ESP_ERR_TIMEOUT;
            break;
        }
        if (received <= 0) {
            transfer_result = ESP_FAIL;
            break;
        }
        timeout_count = 0;
        transfer_result = esp_ota_write(ota_handle,
                                        buffer.get(),
                                        static_cast<std::size_t>(received));
        if (transfer_result != ESP_OK ||
            mbedtls_sha256_update(&sha,
                                  buffer.get(),
                                  static_cast<std::size_t>(received)) != 0) {
            if (transfer_result == ESP_OK) {
                transfer_result = ESP_FAIL;
            }
            break;
        }
        bytes_written += static_cast<std::uint32_t>(received);
        set_progress(bytes_written);
    }

    LOG_INFO(kTag,
             "OTA receive finished bytes=%lu expected=%lu result=%s free_heap=%lu stack_hwm=%u",
             static_cast<unsigned long>(bytes_written),
             static_cast<unsigned long>(image_size),
             esp_err_to_name(transfer_result),
             static_cast<unsigned long>(esp_get_free_heap_size()),
             stack_high_watermark());

    std::array<std::uint8_t, kDigestBytes> computed_digest{};
    if (transfer_result == ESP_OK && bytes_written == image_size) {
        if (mbedtls_sha256_finish(&sha, computed_digest.data()) != 0) {
            transfer_result = ESP_FAIL;
        }
    } else if (transfer_result == ESP_OK) {
        transfer_result = ESP_ERR_INVALID_SIZE;
    }
    mbedtls_sha256_free(&sha);

    std::array<std::uint8_t, kDigestBytes> declared_digest{};
    const bool digest_valid = hex_to_bytes(image_sha256.data(),
                                           std::strlen(image_sha256.data()),
                                           declared_digest.data(),
                                           declared_digest.size());
    if (transfer_result != ESP_OK || !digest_valid ||
        !constant_time_equal(computed_digest.data(),
                             declared_digest.data(),
                             declared_digest.size())) {
        static_cast<void>(esp_ota_abort(ota_handle));
        set_error(transfer_result == ESP_OK
                      ? "image SHA-256 mismatch"
                      : esp_err_to_name(transfer_result));
        return send_error(request,
                          "400 Bad Request",
                          transfer_result == ESP_OK
                              ? "image SHA-256 mismatch"
                              : "OTA transfer was incomplete");
    }

    LOG_INFO(kTag,
             "OTA SHA-256 verified bytes=%lu stack_hwm=%u",
             static_cast<unsigned long>(bytes_written),
             stack_high_watermark());

    LOG_INFO(kTag,
             "OTA image validation begin target=%s free_heap=%lu stack_hwm=%u",
             update_partition->label,
             static_cast<unsigned long>(esp_get_free_heap_size()),
             stack_high_watermark());
    const esp_err_t end_result = esp_ota_end(ota_handle);
    if (end_result != ESP_OK) {
        set_error(esp_err_to_name(end_result));
        return send_error(request,
                          "400 Bad Request",
                          "ESP application image validation failed");
    }
    LOG_INFO(kTag,
             "OTA image validation complete target=%s stack_hwm=%u",
             update_partition->label,
             stack_high_watermark());

    const esp_err_t boot_result = esp_ota_set_boot_partition(update_partition);
    if (boot_result != ESP_OK) {
        set_error(esp_err_to_name(boot_result));
        return send_error(request,
                          "500 Internal Server Error",
                          "cannot select the new boot partition");
    }
    LOG_INFO(kTag,
             "OTA boot partition selected target=%s stack_hwm=%u",
             update_partition->label,
             stack_high_watermark());

    set_success(update_partition->label);
    std::array<char, 320> body{};
    const int body_length = std::snprintf(
        body.data(),
        body.size(),
        "{\"ok\":true,\"result\":\"accepted\",\"node_id\":\"%s\","
        "\"bytes_written\":%lu,\"image_sha256\":\"%s\","
        "\"target_partition\":\"%s\",\"rebooting\":true}",
        credentials_.node_id.data(),
        static_cast<unsigned long>(bytes_written),
        image_sha256.data(),
        update_partition->label);
    if (body_length <= 0 || static_cast<std::size_t>(body_length) >= body.size()) {
        return send_error(request,
                          "500 Internal Server Error",
                          "OTA result serialization failed");
    }

    const esp_err_t response_result = send_json(request, "200 OK", body.data());
    LOG_INFO(kTag,
             "OTA final response result=%s restart_delay_ms=%lu",
             esp_err_to_name(response_result),
             static_cast<unsigned long>(kRestartDelayMs));
    TaskHandle_t restart_handle{};
    if (xTaskCreate(&ServiceOta::restart_task,
                    "wvc_ota_restart",
                    3'072,
                    nullptr,
                    3,
                    &restart_handle) != pdPASS) {
        LOG_WARN(kTag, "new image accepted but restart task could not be created");
    }
    return response_result;
}

void ServiceOta::restart_task(void*)
{
    vTaskDelay(pdMS_TO_TICKS(kRestartDelayMs));
    esp_restart();
    vTaskDelete(nullptr);
}

}  // namespace service_ota
