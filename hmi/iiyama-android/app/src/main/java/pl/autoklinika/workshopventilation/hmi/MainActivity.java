package pl.autoklinika.workshopventilation.hmi;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.nfc.NfcAdapter;
import android.nfc.Tag;
import android.os.Bundle;
import android.os.SystemClock;
import android.text.InputType;
import android.util.Log;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.Toast;

import org.json.JSONObject;

import java.util.Locale;

public class MainActivity extends Activity implements NfcAdapter.ReaderCallback {

    private static final String TAG = "WvcHmiKiosk";
    private static final String SERVICE_TAG = "WvcHmiService";
    private static final String HMI_URL = "http://192.168.1.64:18091/";
    private static final String ALLOWED_SCHEME = "http";
    private static final String ALLOWED_HOST = "192.168.1.64";
    private static final int ALLOWED_PORT = 18091;
    private static final long NFC_DEBOUNCE_MS = 1500L;
    private static final long[] KIOSK_RETRY_DELAYS_MS = {250L, 1000L, 3000L, 7000L};
    private static final int MAX_PIN_ATTEMPTS = 5;
    private static final long PIN_LOCKOUT_MS = 30000L;

    private WebView webView;
    private NfcAdapter nfcAdapter;
    private DevicePolicyManager devicePolicyManager;
    private ComponentName deviceAdminComponent;
    private ServiceAccessStore serviceAccessStore;
    private boolean deviceOwnerPolicyConfigured = false;
    private boolean pageReady = false;
    private boolean serviceExitActive = false;
    private boolean servicePinDialogVisible = false;
    private String pendingNfcEvent = null;
    private String lastUid = null;
    private long lastScanElapsedMs = 0L;
    private int failedPinAttempts = 0;
    private long pinLockoutUntilElapsedMs = 0L;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        serviceAccessStore = new ServiceAccessStore(this);
        devicePolicyManager =
                (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        deviceAdminComponent = new ComponentName(this, KioskDeviceAdminReceiver.class);
        configureDeviceOwnerPolicies();

        webView = new WebView(this);
        webView.setBackgroundColor(Color.BLACK);
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setVerticalScrollBarEnabled(false);
        webView.setHorizontalScrollBarEnabled(false);
        webView.addJavascriptInterface(new KioskJavascriptBridge(), "WvcKioskBridge");

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setUserAgentString(
                settings.getUserAgentString() + " WorkshopVentilationHmi/0.4"
        );

        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, false);
        WebView.setWebContentsDebuggingEnabled(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !isAllowedUri(request.getUrl());
            }

            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
                pageReady = false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);

                Uri uri = Uri.parse(url);
                if (!isAllowedUri(uri)) {
                    pageReady = false;
                    return;
                }

                HmiWebProfile.apply(view);
                HmiServiceGestureProfile.apply(view);
                pageReady = true;
                flushPendingNfcEvent();
            }

            @Override
            public void onReceivedError(
                    WebView view,
                    WebResourceRequest request,
                    WebResourceError error) {
                super.onReceivedError(view, request, error);

                if (!request.isForMainFrame()) {
                    return;
                }

                pageReady = false;
                Toast.makeText(
                        MainActivity.this,
                        "Brak połączenia z CM5 — ponawiam...",
                        Toast.LENGTH_SHORT
                ).show();
                webView.postDelayed(() -> webView.loadUrl(HMI_URL), 3000L);
            }
        });

        setContentView(webView);
        scheduleImmersiveMode();
        scheduleKioskEnforcement();

        nfcAdapter = NfcAdapter.getDefaultAdapter(this);
        webView.loadUrl(HMI_URL);
    }

    private void configureDeviceOwnerPolicies() {
        if (serviceExitActive || deviceOwnerPolicyConfigured) {
            return;
        }

        if (devicePolicyManager == null
                || !devicePolicyManager.isDeviceOwnerApp(getPackageName())) {
            Log.i(TAG, "Device Owner not active; Android lock task remains disabled");
            return;
        }

        try {
            devicePolicyManager.setLockTaskPackages(
                    deviceAdminComponent,
                    new String[]{getPackageName()}
            );
            devicePolicyManager.setLockTaskFeatures(
                    deviceAdminComponent,
                    DevicePolicyManager.LOCK_TASK_FEATURE_NONE
            );
            deviceOwnerPolicyConfigured = true;
            Log.i(TAG, "Device Owner policy configured; package allowlisted for lock task");
        } catch (RuntimeException error) {
            Log.e(TAG, "Unable to configure Device Owner kiosk policy", error);
        }
    }

    private void enterLockTaskIfPermitted() {
        if (serviceExitActive) {
            return;
        }

        if (devicePolicyManager == null
                || !devicePolicyManager.isDeviceOwnerApp(getPackageName())
                || !devicePolicyManager.isLockTaskPermitted(getPackageName())) {
            return;
        }

        ActivityManager activityManager =
                (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        if (activityManager != null
                && activityManager.getLockTaskModeState()
                != ActivityManager.LOCK_TASK_MODE_NONE) {
            return;
        }

        try {
            startLockTask();
            Log.i(TAG, "Android Lock Task Mode entered");
        } catch (RuntimeException error) {
            Log.e(TAG, "Unable to enter Android Lock Task Mode", error);
        }
    }

    private void enforceKioskNow() {
        if (serviceExitActive) {
            return;
        }
        configureDeviceOwnerPolicies();
        enterLockTaskIfPermitted();
    }

    private void scheduleKioskEnforcement() {
        View decorView = getWindow().getDecorView();
        for (long delayMs : KIOSK_RETRY_DELAYS_MS) {
            decorView.postDelayed(() -> {
                if (isFinishing() || isDestroyed() || serviceExitActive) {
                    return;
                }
                enforceKioskNow();
            }, delayMs);
        }
    }

    private boolean isAllowedUri(Uri uri) {
        if (uri == null) {
            return false;
        }

        return ALLOWED_SCHEME.equalsIgnoreCase(uri.getScheme())
                && ALLOWED_HOST.equals(uri.getHost())
                && uri.getPort() == ALLOWED_PORT;
    }

    private void showServicePinDialog() {
        if (servicePinDialogVisible || serviceExitActive) {
            return;
        }

        if (!serviceAccessStore.isPinConfigured()) {
            Log.w(SERVICE_TAG, "Service PIN requested but no PIN is configured yet");
            Toast.makeText(this, "PIN serwisowy nie jest skonfigurowany", Toast.LENGTH_SHORT).show();
            return;
        }

        long now = SystemClock.elapsedRealtime();
        if (now < pinLockoutUntilElapsedMs) {
            long seconds = Math.max(1L, (pinLockoutUntilElapsedMs - now + 999L) / 1000L);
            Toast.makeText(
                    this,
                    "Zbyt wiele prób. Spróbuj za " + seconds + " s",
                    Toast.LENGTH_SHORT
            ).show();
            return;
        }

        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(
                InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD
        );
        input.setHint("PIN");

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Tryb serwisowy")
                .setMessage("Wprowadź PIN serwisowy")
                .setView(input)
                .setNegativeButton("Anuluj", null)
                .setPositiveButton("Odblokuj", null)
                .create();

        servicePinDialogVisible = true;
        dialog.setOnDismissListener(ignored -> servicePinDialogVisible = false);
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(button -> {
                    String pin = input.getText().toString();
                    boolean valid;
                    try {
                        valid = serviceAccessStore.verifyPin(pin);
                    } catch (RuntimeException error) {
                        Log.e(SERVICE_TAG, "Unable to verify service PIN", error);
                        Toast.makeText(
                                MainActivity.this,
                                "Nie udało się zweryfikować PIN-u",
                                Toast.LENGTH_LONG
                        ).show();
                        return;
                    }

                    if (valid) {
                        failedPinAttempts = 0;
                        pinLockoutUntilElapsedMs = 0L;
                        dialog.dismiss();
                        exitKioskToServiceMode("PIN");
                        return;
                    }

                    failedPinAttempts++;
                    input.setText("");
                    input.setError("Nieprawidłowy PIN");

                    if (failedPinAttempts >= MAX_PIN_ATTEMPTS) {
                        failedPinAttempts = 0;
                        pinLockoutUntilElapsedMs =
                                SystemClock.elapsedRealtime() + PIN_LOCKOUT_MS;
                        Log.w(SERVICE_TAG, "Service PIN temporarily locked after failed attempts");
                        dialog.dismiss();
                        Toast.makeText(
                                MainActivity.this,
                                "Zbyt wiele prób. Blokada na 30 s",
                                Toast.LENGTH_LONG
                        ).show();
                    }
                }));

        dialog.show();
        input.requestFocus();
        if (dialog.getWindow() != null) {
            dialog.getWindow().setSoftInputMode(
                    WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE
            );
        }
    }

    private void exitKioskToServiceMode(String method) {
        if (serviceExitActive) {
            return;
        }

        serviceExitActive = true;

        try {
            ActivityManager activityManager =
                    (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);

            if (activityManager != null
                    && activityManager.getLockTaskModeState()
                    != ActivityManager.LOCK_TASK_MODE_NONE) {
                stopLockTask();
            }

            if (devicePolicyManager != null
                    && devicePolicyManager.isDeviceOwnerApp(getPackageName())) {
                devicePolicyManager.setLockTaskPackages(
                        deviceAdminComponent,
                        new String[]{}
                );
                deviceOwnerPolicyConfigured = false;
                Log.i(SERVICE_TAG, "Lock task allowlist suspended for service mode");
            }

            if (activityManager != null
                    && activityManager.getLockTaskModeState()
                    != ActivityManager.LOCK_TASK_MODE_NONE) {
                throw new IllegalStateException("Lock Task remained active after service unlock");
            }
        } catch (RuntimeException error) {
            serviceExitActive = false;
            deviceOwnerPolicyConfigured = false;
            Log.e(SERVICE_TAG, "Unable to leave Android Lock Task Mode", error);
            Toast.makeText(this, "Nie udało się wyjść z kiosku", Toast.LENGTH_LONG).show();
            configureDeviceOwnerPolicies();
            enterLockTaskIfPermitted();
            scheduleKioskEnforcement();
            return;
        }

        showSystemBars();

        Intent serviceIntent = new Intent(this, ServiceAccessActivity.class);
        serviceIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        serviceIntent.putExtra("auth_method", method);

        try {
            startActivity(serviceIntent);
            Log.i(SERVICE_TAG, "Service exit granted via " + method + "; local service screen opened");
            Toast.makeText(this, "Tryb serwisowy", Toast.LENGTH_SHORT).show();
        } catch (RuntimeException error) {
            serviceExitActive = false;
            deviceOwnerPolicyConfigured = false;
            Log.e(SERVICE_TAG, "Unable to open local service screen", error);
            Toast.makeText(this, "Nie udało się otworzyć trybu serwisowego", Toast.LENGTH_LONG).show();
            scheduleImmersiveMode();
            enforceKioskNow();
            scheduleKioskEnforcement();
        }
    }

    private void showSystemBars() {
        View decorView = getWindow().getDecorView();
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController controller = decorView.getWindowInsetsController();
            if (controller != null) {
                controller.show(
                        WindowInsets.Type.statusBars()
                                | WindowInsets.Type.navigationBars()
                );
            }
            return;
        }
        decorView.setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
    }

    @Override
    protected void onResume() {
        super.onResume();

        if (serviceExitActive) {
            serviceExitActive = false;
            Log.i(SERVICE_TAG, "HMI resumed after service mode; kiosk re-armed");
        }

        scheduleImmersiveMode();
        enforceKioskNow();
        scheduleKioskEnforcement();

        if (nfcAdapter == null || !nfcAdapter.isEnabled()) {
            return;
        }

        int flags = NfcAdapter.FLAG_READER_NFC_A
                | NfcAdapter.FLAG_READER_SKIP_NDEF_CHECK;
        nfcAdapter.enableReaderMode(this, this, flags, null);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (nfcAdapter != null) {
            nfcAdapter.disableReaderMode(this);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);

        if (hasFocus && !serviceExitActive) {
            scheduleImmersiveMode();
            enforceKioskNow();
            scheduleKioskEnforcement();
        }
    }

    @Override
    public void onTagDiscovered(Tag tag) {
        byte[] rawUid = tag.getId();
        String uid = toHexCompact(rawUid);

        if (uid.isEmpty() || isDebounced(uid)) {
            return;
        }

        Log.i(SERVICE_TAG, "NFC UID scanned: " + uid);

        if (serviceAccessStore.isServiceCard(uid)) {
            serviceAccessStore.recordCardUse(uid);
            runOnUiThread(() -> exitKioskToServiceMode("NFC:" + uid));
            return;
        }

        try {
            JSONObject detail = new JSONObject();
            detail.put("uid", uid);
            detail.put("uid_display", toHexSpaced(rawUid));
            detail.put("source", "nfc");
            detail.put("timestamp_ms", System.currentTimeMillis());

            String javascript =
                    "window.dispatchEvent(new CustomEvent('wvc:nfc-scan',{detail:"
                            + detail
                            + "}));";

            runOnUiThread(() -> {
                Toast.makeText(
                        MainActivity.this,
                        "NFC: " + uid,
                        Toast.LENGTH_SHORT
                ).show();

                if (pageReady) {
                    webView.evaluateJavascript(javascript, null);
                } else {
                    pendingNfcEvent = javascript;
                }
            });
        } catch (Exception ignored) {
            runOnUiThread(() -> Toast.makeText(
                    MainActivity.this,
                    "Błąd odczytu NFC",
                    Toast.LENGTH_SHORT
            ).show());
        }
    }

    private boolean isDebounced(String uid) {
        long now = SystemClock.elapsedRealtime();

        if (uid.equals(lastUid) && now - lastScanElapsedMs < NFC_DEBOUNCE_MS) {
            return true;
        }

        lastUid = uid;
        lastScanElapsedMs = now;
        return false;
    }

    private void flushPendingNfcEvent() {
        if (pendingNfcEvent == null) {
            return;
        }
        webView.evaluateJavascript(pendingNfcEvent, null);
        pendingNfcEvent = null;
    }

    private static String toHexCompact(byte[] data) {
        if (data == null) {
            return "";
        }

        StringBuilder out = new StringBuilder();
        for (byte value : data) {
            out.append(String.format(Locale.US, "%02X", value & 0xFF));
        }
        return out.toString();
    }

    private static String toHexSpaced(byte[] data) {
        if (data == null) {
            return "";
        }

        StringBuilder out = new StringBuilder();
        for (int i = 0; i < data.length; i++) {
            if (i > 0) {
                out.append(' ');
            }
            out.append(String.format(Locale.US, "%02X", data[i] & 0xFF));
        }
        return out.toString();
    }

    private void scheduleImmersiveMode() {
        View decorView = getWindow().getDecorView();
        decorView.post(this::enterImmersiveMode);
    }

    private void enterImmersiveMode() {
        if (serviceExitActive) {
            return;
        }

        View decorView = getWindow().getDecorView();
        if (android.os.Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController controller = decorView.getWindowInsetsController();
            if (controller != null) {
                controller.hide(
                        WindowInsets.Type.statusBars()
                                | WindowInsets.Type.navigationBars()
                );
                controller.setSystemBarsBehavior(
                        WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                );
            }
            return;
        }

        decorView.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        );
    }

    @Override
    public void onBackPressed() {
        // Intentional: BACK never leaves the normal kiosk surface.
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }

    private final class KioskJavascriptBridge {
        @JavascriptInterface
        public void requestServicePin() {
            runOnUiThread(MainActivity.this::showServicePinDialog);
        }
    }
}
