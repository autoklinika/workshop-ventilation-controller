package pl.autoklinika.workshopventilation.hmi;

import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/** Starts the HMI after Android boot, but only after this package is Device Owner. */
public final class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "WvcHmiBoot";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }

        DevicePolicyManager dpm =
                (DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);

        if (dpm == null || !dpm.isDeviceOwnerApp(context.getPackageName())) {
            Log.i(TAG, "BOOT_COMPLETED ignored: package is not Device Owner");
            return;
        }

        Intent launch = new Intent(context, MainActivity.class);
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        context.startActivity(launch);
        Log.i(TAG, "HMI launch requested after BOOT_COMPLETED");
    }
}
