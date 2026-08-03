#pragma once

#include "esp_err.h"

namespace platform {

class StatusLed final {
public:
    esp_err_t initialize();
    esp_err_t set(bool enabled) const;

private:
    bool initialized_{false};
};

}  // namespace platform
