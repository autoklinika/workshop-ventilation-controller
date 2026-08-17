idf_component_register(
    SRCS
        "src/register_map.cpp"
        "src/modbus_rtu_slave.cpp"
    INCLUDE_DIRS "include"
    REQUIRES
        config
        diagnostics
        freertos
        logging
        sen55
        esp_driver_uart
        esp_timer
        espressif__esp-modbus
)

target_compile_definitions(${COMPONENT_LIB} PRIVATE WVC_FORCE_SEN55_FAN_ALERT_TEST=1)
