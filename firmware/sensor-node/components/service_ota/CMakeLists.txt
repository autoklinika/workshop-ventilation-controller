idf_component_register(
    SRCS "src/service_ota.cpp"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "compat_include"
    REQUIRES
        app_update
        config
        esp_http_server
        esp_system
        esp_timer
        freertos
        logging
        mbedtls
)
