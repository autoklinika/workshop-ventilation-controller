#include "sen55/sen55_crc.hpp"

namespace sen55 {

std::uint8_t calculate_crc(const std::uint8_t* data, const std::size_t size)
{
    std::uint8_t crc = 0xFF;
    for (std::size_t index = 0; index < size; ++index) {
        crc ^= data[index];
        for (std::uint8_t bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x80U) != 0U ? static_cast<std::uint8_t>((crc << 1U) ^ 0x31U)
                                      : static_cast<std::uint8_t>(crc << 1U);
        }
    }
    return crc;
}

esp_err_t decode_crc_words(const std::uint8_t* encoded,
                           const std::size_t encoded_size,
                           std::uint8_t* decoded,
                           const std::size_t decoded_size)
{
    if (encoded == nullptr || decoded == nullptr || encoded_size == 0 || encoded_size % 3 != 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (decoded_size != (encoded_size / 3) * 2) {
        return ESP_ERR_INVALID_SIZE;
    }

    std::size_t decoded_index = 0;
    for (std::size_t encoded_index = 0; encoded_index < encoded_size; encoded_index += 3) {
        if (calculate_crc(&encoded[encoded_index], 2) != encoded[encoded_index + 2]) {
            return ESP_ERR_INVALID_CRC;
        }
        decoded[decoded_index++] = encoded[encoded_index];
        decoded[decoded_index++] = encoded[encoded_index + 1];
    }
    return ESP_OK;
}

}  // namespace sen55
