idf_component_register(
    SRCS "src/boot_info.cpp" "src/ota_health_guard.cpp" "src/status_led.cpp"
    INCLUDE_DIRS "include"
    REQUIRES app_update esp_app_format esp_partition esp_system esp_timer esp_driver_gpio logging config
)
