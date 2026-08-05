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

# ESP-IDF's esp_netif_config_t has an optional driver field. The designated
# initializer intentionally leaves it zero-initialized because the Wi-Fi
# station is attached explicitly with esp_netif_attach_wifi_station().
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error=missing-field-initializers)
