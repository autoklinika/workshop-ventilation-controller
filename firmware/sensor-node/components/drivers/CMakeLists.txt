idf_component_register(
    SRCS "src/i2c_bus.cpp"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_i2c freertos logging config
)
