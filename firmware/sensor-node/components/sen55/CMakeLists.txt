idf_component_register(
    SRCS "src/sen55.cpp" "src/sen55_crc.cpp"
    INCLUDE_DIRS "include"
    REQUIRES drivers esp_timer logging config
)
