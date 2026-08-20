package pl.autoklinika.workshopventilation.hmi;

import android.app.Activity;
import android.app.Application;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import android.util.Log;

/**
 * Application-wide owner of the iiyama RGB status LED controller.
 *
 * The controller is intentionally independent from WebView JavaScript. It polls the
 * existing ventilation-core alert API directly and keeps the local LED state alive
 * across MainActivity / service activities while the HMI process exists.
 */
public final class HmiApplication extends Application {

    private static final String TAG = "WvcHmiLed";
    private static final String ACTION_LED_DIAGNOSTIC =
            "pl.autoklinika.workshopventilation.hmi.LED_DIAGNOSTIC";

    private HmiLedController ledController;
    private BroadcastReceiver ledDiagnosticReceiver;

    @Override
    public void onCreate() {
        super.onCreate();
        ledController = new HmiLedController();
        ledController.start();

        if (BuildConfig.DEBUG) {
            registerLedDiagnosticReceiver();
        }

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

    private void registerLedDiagnosticReceiver() {
        ledDiagnosticReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                String requestedState = intent.getStringExtra("state");
                boolean accepted = ledController.setDiagnosticOverride(requestedState);
                Log.i(TAG, "LED DIAGNOSTIC broadcast state=" + requestedState
                        + " accepted=" + accepted);
                setResultCode(accepted ? Activity.RESULT_OK : Activity.RESULT_CANCELED);
            }
        };

        IntentFilter filter = new IntentFilter(ACTION_LED_DIAGNOSTIC);
        registerReceiver(ledDiagnosticReceiver, filter, Context.RECEIVER_EXPORTED);
        Log.i(TAG, "LED DIAGNOSTIC receiver enabled for debug build");
    }
}
