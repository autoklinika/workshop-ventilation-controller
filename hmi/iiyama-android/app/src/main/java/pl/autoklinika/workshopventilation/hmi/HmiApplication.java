package pl.autoklinika.workshopventilation.hmi;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;

/**
 * Application-wide owner of the iiyama RGB status LED controller.
 *
 * The controller is intentionally independent from WebView JavaScript. It polls the
 * existing ventilation-core alert API directly and keeps the local LED state alive
 * across MainActivity / service activities while the HMI process exists.
 */
public final class HmiApplication extends Application {

    private HmiLedController ledController;

    @Override
    public void onCreate() {
        super.onCreate();
        ledController = new HmiLedController();
        ledController.start();

        registerActivityLifecycleCallbacks(new ActivityLifecycleCallbacks() {
            @Override
            public void onActivityCreated(Activity activity, Bundle savedInstanceState) {
            }

            @Override
            public void onActivityStarted(Activity activity) {
            }

            @Override
            public void onActivityResumed(Activity activity) {
                if (activity instanceof ServiceModeActivity || activity instanceof ServiceAccessActivity) {
                    ledController.setLocalServiceMode(true);
                } else if (activity instanceof MainActivity) {
                    ledController.setLocalServiceMode(false);
                }
            }

            @Override
            public void onActivityPaused(Activity activity) {
            }

            @Override
            public void onActivityStopped(Activity activity) {
            }

            @Override
            public void onActivitySaveInstanceState(Activity activity, Bundle outState) {
            }

            @Override
            public void onActivityDestroyed(Activity activity) {
            }
        });
    }
}
