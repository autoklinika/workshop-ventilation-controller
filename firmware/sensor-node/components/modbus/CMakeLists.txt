idf_component_register(
    SRCS
        "src/register_map.cpp"
        "src/modbus_rtu_slave.cpp"
    INCLUDE_DIRS "include"
    REQUIRES
        config
        diagnostics
        logging
        sen55
        driver
        esp_timer
        esp_modbus
)
