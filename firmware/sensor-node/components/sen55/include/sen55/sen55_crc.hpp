#pragma once

#include <cstddef>
#include <cstdint>

#include "esp_err.h"

namespace sen55 {

std::uint8_t calculate_crc(const std::uint8_t* data, std::size_t size);
esp_err_t decode_crc_words(const std::uint8_t* encoded,
                           std::size_t encoded_size,
                           std::uint8_t* decoded,
                           std::size_t decoded_size);

}  // namespace sen55
