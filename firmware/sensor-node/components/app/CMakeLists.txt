idf_component_register(
    SRCS "src/application.cpp"
    INCLUDE_DIRS "include"
    REQUIRES services modbus platform drivers diagnostics logging config freertos esp_system esp_timer
)
