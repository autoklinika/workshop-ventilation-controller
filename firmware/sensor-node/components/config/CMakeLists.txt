idf_component_register(
    SRCS
        "src/modbus_address.cpp"
    INCLUDE_DIRS "include"
    REQUIRES
        esp_driver_gpio
        esp_driver_i2c
        esp_driver_uart
        nvs_flash
)
