#pragma once

#include <cstdint>

#include "esp_err.h"

namespace platform {

class OtaHealthGuard final {
public:
    esp_err_t initialize();
    esp_err_t confirm_if_due(bool platform_healthy);

    [[nodiscard]] bool confirmation_pending() const;

private:
    bool pending_{false};
    std::int64_t started_us_{0};
};

}  // namespace platform
