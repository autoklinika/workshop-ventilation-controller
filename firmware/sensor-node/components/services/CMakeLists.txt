idf_component_register(
    SRCS "src/sensor_service.cpp"
    INCLUDE_DIRS "include"
    REQUIRES sen55 diagnostics esp_timer logging config
)
