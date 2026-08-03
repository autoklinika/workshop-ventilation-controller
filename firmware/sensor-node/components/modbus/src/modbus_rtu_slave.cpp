#include "modbus/modbus_rtu_slave.hpp"

#include <algorithm>
#include <cstdint>
#include <limits>

#include "config/board_config.hpp"
#include "config/firmware_config.hpp"
#include "driver/uart.h"
#include "esp_timer.h"
#include "logging/log.hpp"
#include "mbcontroller.h"

namespace modbus {
namespace {
constexpr char kTag[] = "modbus_rtu";
constexpr std::uint16_t kInputRegisterStart = 0;
constexpr std::uint8_t kAllMeasurementFieldsAvailable = 0xFFU;

std::uint32_t saturate_u32(const std::uint64_t value)
{
    return static_cast<std::uint32_t>(std::min<std::uint64_t>(
        value, std::numeric_limits<std::uint32_t>::max()));
}

std::uint16_t age_seconds(const std::int64_t now_us,
                          const std::int64_t last_success_us)
{
    if (last_success_us <= 0 || now_us < last_success_us) {
        return std::numeric_limits<std::uint16_t>::max();
    }

    const std::uint64_t seconds = static_cast<std::uint64_t>(
        (now_us - last_success_us) / 1'000'000);
    return static_cast<std::uint16_t>(std::min<std::uint64_t>(
        seconds, std::numeric_limits<std::uint16_t>::max()));
}

}  // namespace

ModbusRtuSlave::~ModbusRtuSlave()
{
    destroy();
}

esp_err_t ModbusRtuSlave::initialize()
{
    if (handle_ != nullptr) {
        return ESP_OK;
    }

    RegisterSource initial_source{};
    initial_source.measurement_stale = true;
    initial_source.initializing = true;
    initial_source.firmware_version = config::firmware::kFirmwareVersionPacked;
    registers_ = encode_input_registers(initial_source);

    mb_communication_info_t communication{};
    communication.ser_opts.port = config::board::kRs485Uart;
    communication.ser_opts.mode = MB_RTU;
    communication.ser_opts.baudrate = config::firmware::kModbusBaudRate;
    communication.ser_opts.parity = MB_PARITY_NONE;
    communication.ser_opts.uid = config::firmware::kModbusSlaveAddress;
    communication.ser_opts.data_bits = UART_DATA_8_BITS;
    communication.ser_opts.stop_bits = UART_STOP_BITS_1;

    esp_err_t result = mbc_slave_create_serial(&communication, &handle_);
    if (result != ESP_OK || handle_ == nullptr) {
        if (result == ESP_OK) {
            result = ESP_FAIL;
        }
        handle_ = nullptr;
        record_service_error(result, "mbc_slave_create_serial");
        return result;
    }

    mb_register_area_descriptor_t input_area{};
    input_area.type = MB_PARAM_INPUT;
    input_area.start_offset = kInputRegisterStart;
    input_area.access = MB_ACCESS_RO;
    input_area.address = registers_.data();
    input_area.size = sizeof(registers_);

    result = mbc_slave_set_descriptor(handle_, input_area);
    if (result != ESP_OK) {
        record_service_error(result, "mbc_slave_set_descriptor");
        destroy();
        return result;
    }

    result = uart_set_pin(config::board::kRs485Uart,
                          config::board::kRs485Tx,
                          config::board::kRs485Rx,
                          config::board::kRs485Direction,
                          UART_PIN_NO_CHANGE);
    if (result != ESP_OK) {
        record_service_error(result, "uart_set_pin");
        destroy();
        return result;
    }

    result = uart_set_mode(config::board::kRs485Uart,
                           UART_MODE_RS485_HALF_DUPLEX);
    if (result != ESP_OK) {
        record_service_error(result, "uart_set_mode");
        destroy();
        return result;
    }

    result = mbc_slave_start(handle_);
    if (result != ESP_OK) {
        record_service_error(result, "mbc_slave_start");
        destroy();
        return result;
    }

    LOG_INFO(kTag,
             "started: mode=RTU address=%u baud=%lu format=8N1 uart=%d tx=%d rx=%d de_re=%d input_registers=%u",
             static_cast<unsigned>(config::firmware::kModbusSlaveAddress),
             static_cast<unsigned long>(config::firmware::kModbusBaudRate),
             static_cast<int>(config::board::kRs485Uart),
             static_cast<int>(config::board::kRs485Tx),
             static_cast<int>(config::board::kRs485Rx),
             static_cast<int>(config::board::kRs485Direction),
             static_cast<unsigned>(kInputRegisterCount));
    return ESP_OK;
}

esp_err_t ModbusRtuSlave::refresh(const sen55::Measurement& measurement,
                                  const diagnostics::Snapshot& snapshot)
{
    if (handle_ == nullptr) {
        return ESP_ERR_INVALID_STATE;
    }

    const std::int64_t now_us = esp_timer_get_time();
    if (last_refresh_us_ > 0 &&
        (now_us - last_refresh_us_) <
            static_cast<std::int64_t>(config::firmware::kModbusRegisterRefreshPeriodMs) * 1000) {
        return ESP_OK;
    }
    last_refresh_us_ = now_us;

    const InputRegisterBank next = encode_input_registers(
        build_source(measurement, snapshot, now_us));

    esp_err_t result = mbc_slave_lock(handle_);
    if (result != ESP_OK) {
        record_service_error(result, "mbc_slave_lock");
        return result;
    }

    registers_ = next;

    result = mbc_slave_unlock(handle_);
    if (result != ESP_OK) {
        record_service_error(result, "mbc_slave_unlock");
        return result;
    }
    return ESP_OK;
}

bool ModbusRtuSlave::initialized() const
{
    return handle_ != nullptr;
}

std::uint32_t ModbusRtuSlave::service_error_count() const
{
    return service_error_count_;
}

const InputRegisterBank& ModbusRtuSlave::register_bank() const
{
    return registers_;
}

RegisterSource ModbusRtuSlave::build_source(
    const sen55::Measurement& measurement,
    const diagnostics::Snapshot& snapshot,
    const std::int64_t now_us) const
{
    RegisterSource source{};
    source.pm1_0 = measurement.pm1_0;
    source.pm2_5 = measurement.pm2_5;
    source.pm4_0 = measurement.pm4_0;
    source.pm10_0 = measurement.pm10_0;
    source.humidity_percent = measurement.humidity_percent;
    source.temperature_celsius = measurement.temperature_celsius;
    source.voc_index = measurement.voc_index;
    source.nox_index = measurement.nox_index;
    source.availability_mask = measurement.availability_mask;

    source.measurement_age_seconds = age_seconds(now_us,
                                                  snapshot.last_success_us);
    const bool sensor_running =
        snapshot.sensor_state == diagnostics::SensorState::kRunning;
    const bool age_invalid =
        source.measurement_age_seconds == std::numeric_limits<std::uint16_t>::max();
    const bool age_expired = !age_invalid &&
        static_cast<std::uint32_t>(source.measurement_age_seconds) * 1000U >
            config::firmware::kMeasurementStaleAfterMs;
    const bool stale = !snapshot.first_measurement_received ||
                       !sensor_running ||
                       age_invalid ||
                       age_expired;

    source.measurement_valid = snapshot.first_measurement_received &&
                               sensor_running &&
                               !stale &&
                               measurement.availability_mask != 0;
    source.sensor_present = snapshot.sensor_present;
    source.measurement_stale = stale;
    source.i2c_error = snapshot.last_error != ESP_OK &&
                       snapshot.last_error != ESP_ERR_INVALID_CRC;
    source.data_error = snapshot.last_error == ESP_ERR_INVALID_CRC ||
                        (snapshot.first_measurement_received &&
                         measurement.availability_mask != kAllMeasurementFieldsAvailable);
    source.initializing =
        snapshot.sensor_state == diagnostics::SensorState::kUninitialized ||
        snapshot.sensor_state == diagnostics::SensorState::kDetecting ||
        snapshot.sensor_state == diagnostics::SensorState::kWaitingForFirstMeasurement;
    source.sensor_offline =
        snapshot.sensor_state == diagnostics::SensorState::kOffline;
    source.platform_fault = !snapshot.gpio_ready ||
                            !snapshot.i2c_ready ||
                            !snapshot.rs485_ready;

    const std::uint64_t sensor_errors =
        static_cast<std::uint64_t>(snapshot.detection_failures) +
        snapshot.communication_failures + snapshot.crc_failures;
    source.sensor_error_count = saturate_u32(sensor_errors);
    source.modbus_service_error_count = service_error_count_;
    source.uptime_seconds = static_cast<std::uint32_t>(
        static_cast<std::uint64_t>(now_us) / 1'000'000U);
    source.firmware_version = config::firmware::kFirmwareVersionPacked;
    source.measurement_sequence = measurement.sequence;
    return source;
}

void ModbusRtuSlave::record_service_error(const esp_err_t error,
                                          const char* operation)
{
    ++service_error_count_;
    LOG_ERROR(kTag,
              "%s failed: %s service_errors=%lu",
              operation,
              esp_err_to_name(error),
              static_cast<unsigned long>(service_error_count_));
}

void ModbusRtuSlave::destroy()
{
    if (handle_ == nullptr) {
        return;
    }

    const esp_err_t result = mbc_slave_delete(handle_);
    if (result != ESP_OK) {
        record_service_error(result, "mbc_slave_delete");
    }
    handle_ = nullptr;
}

}  // namespace modbus
