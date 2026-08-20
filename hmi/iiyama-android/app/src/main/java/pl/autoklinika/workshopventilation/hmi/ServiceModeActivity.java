package pl.autoklinika.workshopventilation.hmi;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.os.SystemClock;
import android.text.InputType;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;

/** First service-mode screen shown after a service NFC card or the normal service PIN. */
public final class ServiceModeActivity extends Activity {

    private static final String TAG = "WvcHmiService";
    private static final int BG = Color.rgb(9, 18, 28);
    private static final int TILE = Color.rgb(18, 31, 45);
    private static final int TEXT = Color.WHITE;
    private static final int MUTED = Color.rgb(174, 190, 205);
    private static final int MAX_ADMIN_PIN_ATTEMPTS = 5;
    private static final long ADMIN_PIN_LOCKOUT_MS = 30000L;
    private static final String ADMIN_PIN_SALT = "wvc-iiyama-admin-settings-v1";

    private int failedAdminPinAttempts = 0;
    private long adminPinLockoutUntilElapsedMs = 0L;
    private boolean adminPinDialogVisible = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(buildUi());
    }

    private View buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setBackgroundColor(BG);
        root.setPadding(dp(48), dp(38), dp(48), dp(38));

        TextView title = text("TRYB SERWISOWY", 30, TEXT);
        title.setTypeface(title.getTypeface(), android.graphics.Typeface.BOLD);
        title.setGravity(Gravity.CENTER);
        root.addView(title);

        TextView subtitle = text("Wybierz działanie", 16, MUTED);
        subtitle.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        subtitleParams.topMargin = dp(6);
        root.addView(subtitle, subtitleParams);

        LinearLayout tiles = new LinearLayout(this);
        tiles.setOrientation(LinearLayout.HORIZONTAL);
        tiles.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams tilesParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f
        );
        tilesParams.topMargin = dp(34);
        root.addView(tiles, tilesParams);

        View androidTile = tile(
                "ANDROID",
                "Wyjdź z kiosku i przejdź do systemu Android",
                this::exitToAndroid
        );
        LinearLayout.LayoutParams androidParams = new LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.MATCH_PARENT,
                1f
        );
        androidParams.rightMargin = dp(14);
        tiles.addView(androidTile, androidParams);

        View settingsTile = tile(
                "USTAWIENIA",
                "Karty NFC i PIN serwisowy",
                this::showAdministratorPinDialog
        );
        LinearLayout.LayoutParams settingsParams = new LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.MATCH_PARENT,
                1f
        );
        settingsParams.leftMargin = dp(14);
        tiles.addView(settingsTile, settingsParams);

        TextView back = text("WRÓĆ DO HMI", 15, TEXT);
        back.setGravity(Gravity.CENTER);
        back.setPadding(dp(24), dp(18), dp(24), dp(18));
        back.setBackgroundColor(TILE);
        back.setClickable(true);
        back.setFocusable(true);
        back.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams backParams = new LinearLayout.LayoutParams(
                dp(240),
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        backParams.topMargin = dp(28);
        root.addView(back, backParams);

        return root;
    }

    private View tile(String titleValue, String subtitleValue, Runnable action) {
        LinearLayout tile = new LinearLayout(this);
        tile.setOrientation(LinearLayout.VERTICAL);
        tile.setGravity(Gravity.CENTER);
        tile.setPadding(dp(34), dp(34), dp(34), dp(34));
        tile.setBackgroundColor(TILE);
        tile.setClickable(true);
        tile.setFocusable(true);

        TextView title = text(titleValue, 28, TEXT);
        title.setTypeface(title.getTypeface(), android.graphics.Typeface.BOLD);
        title.setGravity(Gravity.CENTER);
        tile.addView(title);

        TextView subtitle = text(subtitleValue, 15, MUTED);
        subtitle.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        subtitleParams.topMargin = dp(14);
        tile.addView(subtitle, subtitleParams);
        tile.setOnClickListener(v -> action.run());
        return tile;
    }

    private void showAdministratorPinDialog() {
        if (adminPinDialogVisible) {
            return;
        }
        if (BuildConfig.ADMIN_SETTINGS_PIN_SHA256 == null
                || BuildConfig.ADMIN_SETTINGS_PIN_SHA256.isEmpty()) {
            Toast.makeText(this, "PIN ustawień nie jest skonfigurowany", Toast.LENGTH_LONG).show();
            return;
        }

        long now = SystemClock.elapsedRealtime();
        if (now < adminPinLockoutUntilElapsedMs) {
            long seconds = Math.max(1L, (adminPinLockoutUntilElapsedMs - now + 999L) / 1000L);
            Toast.makeText(this, "Zbyt wiele prób. Spróbuj za " + seconds + " s", Toast.LENGTH_SHORT).show();
            return;
        }

        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setHint("PIN ustawień");
        input.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Ustawienia serwisowe")
                .setMessage("Wprowadź stały PIN administratora")
                .setView(input)
                .setNegativeButton("Anuluj", null)
                .setPositiveButton("Otwórz", null)
                .create();

        adminPinDialogVisible = true;
        dialog.setOnDismissListener(ignored -> adminPinDialogVisible = false);
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(v -> {
                    if (matchesAdministratorPin(input.getText().toString())) {
                        failedAdminPinAttempts = 0;
                        adminPinLockoutUntilElapsedMs = 0L;
                        dialog.dismiss();
                        openServiceSettings();
                        return;
                    }

                    failedAdminPinAttempts++;
                    input.setText("");
                    input.setError("Nieprawidłowy PIN");
                    if (failedAdminPinAttempts >= MAX_ADMIN_PIN_ATTEMPTS) {
                        failedAdminPinAttempts = 0;
                        adminPinLockoutUntilElapsedMs = SystemClock.elapsedRealtime() + ADMIN_PIN_LOCKOUT_MS;
                        dialog.dismiss();
                        Toast.makeText(this, "Zbyt wiele prób. Blokada na 30 s", Toast.LENGTH_LONG).show();
                    }
                }));

        dialog.show();
        input.requestFocus();
        if (dialog.getWindow() != null) {
            dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE);
        }
    }

    private void openServiceSettings() {
        try {
            Intent intent = new Intent(this, ServiceAccessActivity.class);
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
            startActivity(intent);
            Log.i(TAG, "Service access settings opened after fixed administrator PIN");
        } catch (RuntimeException error) {
            Log.e(TAG, "Unable to open service access settings", error);
            Toast.makeText(this, "Nie udało się otworzyć ustawień", Toast.LENGTH_LONG).show();
        }
    }

    private void exitToAndroid() {
        DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        ComponentName admin = new ComponentName(this, KioskDeviceAdminReceiver.class);
        ActivityManager activityManager = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);

        try {
            if (activityManager != null
                    && activityManager.getLockTaskModeState() != ActivityManager.LOCK_TASK_MODE_NONE) {
                stopLockTask();
            }
            if (dpm != null && dpm.isDeviceOwnerApp(getPackageName())) {
                dpm.setLockTaskPackages(admin, new String[]{});
                Log.i(TAG, "Lock task allowlist suspended for Android service exit");
            }
            if (activityManager != null
                    && activityManager.getLockTaskModeState() != ActivityManager.LOCK_TASK_MODE_NONE) {
                try {
                    stopLockTask();
                } catch (RuntimeException ignored) {
                    // Final state is checked below.
                }
            }
            if (activityManager != null
                    && activityManager.getLockTaskModeState() != ActivityManager.LOCK_TASK_MODE_NONE) {
                throw new IllegalStateException("Lock Task remained active after Android exit request");
            }
        } catch (RuntimeException error) {
            Log.e(TAG, "Unable to leave kiosk for Android", error);
            Toast.makeText(this, "Nie udało się wyjść z kiosku", Toast.LENGTH_LONG).show();
            return;
        }

        showSystemBars();
        Intent home = new Intent(Intent.ACTION_MAIN);
        home.addCategory(Intent.CATEGORY_HOME);
        home.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
        try {
            startActivity(home);
            Log.i(TAG, "Android service exit granted; launcher opened");
            finishAndRemoveTask();
        } catch (RuntimeException error) {
            Log.e(TAG, "Unable to open Android launcher", error);
            Toast.makeText(this, "Nie udało się otworzyć Androida", Toast.LENGTH_LONG).show();
        }
    }

    private void showSystemBars() {
        View decorView = getWindow().getDecorView();
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController controller = decorView.getWindowInsetsController();
            if (controller != null) {
                controller.show(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
            }
            return;
        }
        decorView.setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
    }

    private static boolean matchesAdministratorPin(String pin) {
        if (pin == null) {
            return false;
        }
        String candidate = sha256Hex(ADMIN_PIN_SALT + ":" + pin);
        return MessageDigest.isEqual(
                candidate.getBytes(StandardCharsets.US_ASCII),
                BuildConfig.ADMIN_SETTINGS_PIN_SHA256.getBytes(StandardCharsets.US_ASCII)
        );
    }

    private static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder(hash.length * 2);
            for (byte item : hash) {
                out.append(String.format(Locale.US, "%02x", item & 0xFF));
            }
            return out.toString();
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private TextView text(String value, int sp, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        return view;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
