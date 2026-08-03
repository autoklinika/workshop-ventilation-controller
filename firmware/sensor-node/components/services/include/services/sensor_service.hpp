#pragma once

#include <cstdint>

#include "diagnostics/diagnostics.hpp"
#include "esp_err.h"
#include "sen55/sen55.hpp"
#include "sen55/sen55_types.hpp"

namespace services {

class SensorService final {
public:
    SensorService(sen55::Sen55& sensor, diagnostics::Diagnostics& diagnostics);

    void start();
    void poll();

    [[nodiscard]] bool online() const;
    [[nodiscard]] bool has_new_measurement(std::uint64_t last_sequence) const;
    [[nodiscard]] const sen55::Measurement& latest_measurement() const;
    [[nodiscard]] const sen55::DeviceInfo& device_info() const;

private:
    void connect();
    void handle_error(esp_err_t error, const char* operation);
    void set_offline(esp_err_t error);

    sen55::Sen55& sensor_;
    diagnostics::Diagnostics& diagnostics_;
    sen55::DeviceInfo device_info_{};
    sen55::Measurement latest_measurement_{};
    std::uint64_t sequence_{0};
    std::uint32_t consecutive_errors_{0};
    std::int64_t state_started_us_{0};
    std::int64_t last_poll_us_{0};
    std::int64_t last_connect_attempt_us_{0};
};

}  // namespace services
