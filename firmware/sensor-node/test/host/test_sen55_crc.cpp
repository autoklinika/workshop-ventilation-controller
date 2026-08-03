#include <array>
#include <cassert>
#include <cstdint>

#include "sen55/sen55_crc.hpp"

int main()
{
    // Official Sensirion CRC example: 0xBEEF -> CRC 0x92.
    const std::array<std::uint8_t, 2> word{0xBE, 0xEF};
    assert(sen55::calculate_crc(word.data(), word.size()) == 0x92);

    const std::array<std::uint8_t, 6> encoded{0xBE, 0xEF, 0x92, 0x00, 0x00, 0x81};
    std::array<std::uint8_t, 4> decoded{};
    assert(sen55::decode_crc_words(encoded.data(), encoded.size(), decoded.data(), decoded.size()) == ESP_OK);
    assert(decoded[0] == 0xBE && decoded[1] == 0xEF && decoded[2] == 0x00 && decoded[3] == 0x00);

    auto corrupted = encoded;
    corrupted[2] ^= 0x01;
    assert(sen55::decode_crc_words(corrupted.data(), corrupted.size(), decoded.data(), decoded.size()) == ESP_ERR_INVALID_CRC);
    return 0;
}
