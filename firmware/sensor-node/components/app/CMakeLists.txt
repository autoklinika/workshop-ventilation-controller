idf_component_register(
    SRCS "src/application.cpp"
    INCLUDE_DIRS "include"
    REQUIRES services modbus platform drivers diagnostics logging config service_ota service_wifi freertos esp_system esp_timer
)
