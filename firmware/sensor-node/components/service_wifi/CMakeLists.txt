idf_component_register(
    SRCS "src/service_wifi.cpp"
    INCLUDE_DIRS "include"
    REQUIRES
        app_update
        config
        esp_event
        esp_netif
        esp_system
        esp_timer
        esp_wifi
        freertos
        logging
        lwip
        mbedtls
)
