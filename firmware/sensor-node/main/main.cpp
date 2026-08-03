#include "app/application.hpp"

extern "C" void app_main(void)
{
    app::Application application;
    application.run();
}
