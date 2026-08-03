#include <cassert>
#include <cstdint>
#include <limits>

#include "modbus/register_map.hpp"

namespace {

std::uint16_t at(const modbus::InputRegisterBank& bank,
                 const modbus::InputRegister reg)
{
    return bank[static_cast<std::size_t>(reg)];
}

void test_complete_measurement()
{
    modbus::RegisterSource source{};
    source.pm1_0 = 12.3F;
    source.pm2_5 = 45.6F;
    source.pm4_0 = 78.9F;
    source.pm10_0 = 101.2F;
    source.humidity_percent = 54.32F;
    source.temperature_celsius = -5.25F;
    source.voc_index = 123.4F;
    source.nox_index = 56.7F;
    source.availability_mask = 0xFFU;
    source.measurement_valid = true;
    source.sensor_present = true;
    source.measurement_stale = false;
    source.initializing = false;
    source.measurement_age_seconds = 2;
    source.sensor_error_count = 7;
    source.modbus_service_error_count = 3;
    source.uptime_seconds = 0x12345678U;
    source.firmware_version = 0x0002U;
    source.measurement_sequence = 0xABCDEF0123456789ULL;

    const auto bank = modbus::encode_input_registers(source);

    assert(at(bank, modbus::InputRegister::kPm1_0) == 123U);
    assert(at(bank, modbus::InputRegister::kPm2_5) == 456U);
    assert(at(bank, modbus::InputRegister::kPm4_0) == 789U);
    assert(at(bank, modbus::InputRegister::kPm10_0) == 1012U);
    assert(at(bank, modbus::InputRegister::kHumidity) == 5432U);
    assert(at(bank, modbus::InputRegister::kTemperature) ==
           static_cast<std::uint16_t>(static_cast<std::int16_t>(-525)));
    assert(at(bank, modbus::InputRegister::kVocIndex) == 1234U);
    assert(at(bank, modbus::InputRegister::kNoxIndex) == 567U);
    assert(at(bank, modbus::InputRegister::kAvailabilityMask) == 0x00FFU);
    assert(at(bank, modbus::InputRegister::kNodeStatus) ==
           (modbus::kMeasurementValid | modbus::kSensorPresent));
    assert(at(bank, modbus::InputRegister::kMeasurementAgeSeconds) == 2U);
    assert(at(bank, modbus::InputRegister::kSensorErrorCount) == 7U);
    assert(at(bank, modbus::InputRegister::kModbusServiceErrorCount) == 3U);
    assert(at(bank, modbus::InputRegister::kUptimeHigh) == 0x1234U);
    assert(at(bank, modbus::InputRegister::kUptimeLow) == 0x5678U);
    assert(at(bank, modbus::InputRegister::kFirmwareVersion) == 0x0002U);
    assert(at(bank, modbus::InputRegister::kRegisterMapVersion) == 1U);
    assert(at(bank, modbus::InputRegister::kMeasurementSequenceHigh) == 0x2345U);
    assert(at(bank, modbus::InputRegister::kMeasurementSequenceLow) == 0x6789U);
}

void test_unavailable_and_status_fields()
{
    modbus::RegisterSource source{};
    source.pm1_0 = 100.0F;
    source.temperature_celsius = 20.0F;
    source.availability_mask = 0;
    source.measurement_stale = true;
    source.i2c_error = true;
    source.data_error = true;
    source.initializing = true;
    source.sensor_offline = true;
    source.platform_fault = true;
    source.measurement_age_seconds = 0xFFFFU;
    source.sensor_error_count = std::numeric_limits<std::uint32_t>::max();
    source.modbus_service_error_count = std::numeric_limits<std::uint32_t>::max();

    const auto bank = modbus::encode_input_registers(source);

    assert(at(bank, modbus::InputRegister::kPm1_0) == 0U);
    assert(at(bank, modbus::InputRegister::kTemperature) == 0U);
    assert(at(bank, modbus::InputRegister::kAvailabilityMask) == 0U);
    assert(at(bank, modbus::InputRegister::kNodeStatus) ==
           (modbus::kMeasurementStale |
            modbus::kI2cError |
            modbus::kDataError |
            modbus::kInitializing |
            modbus::kSensorOffline |
            modbus::kPlatformFault));
    assert(at(bank, modbus::InputRegister::kSensorErrorCount) == 0xFFFFU);
    assert(at(bank, modbus::InputRegister::kModbusServiceErrorCount) == 0xFFFFU);
}

void test_scaling_saturation()
{
    modbus::RegisterSource source{};
    source.availability_mask = 0xFFU;
    source.pm1_0 = -10.0F;
    source.pm2_5 = 1.0e9F;
    source.temperature_celsius = 1.0e9F;

    const auto bank = modbus::encode_input_registers(source);

    assert(at(bank, modbus::InputRegister::kPm1_0) == 0U);
    assert(at(bank, modbus::InputRegister::kPm2_5) == 0xFFFFU);
    assert(at(bank, modbus::InputRegister::kTemperature) == 0x7FFFU);
}

}  // namespace

int main()
{
    test_complete_measurement();
    test_unavailable_and_status_fields();
    test_scaling_saturation();
    return 0;
}
