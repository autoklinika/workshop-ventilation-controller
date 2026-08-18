package pl.autoklinika.workshopventilation.hmi;

import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.nfc.NfcAdapter;
import android.nfc.Tag;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.util.Locale;

public class MainActivity extends Activity implements NfcAdapter.ReaderCallback {

    private static final String HMI_URL = "http://192.168.1.64:18091/";
    private static final String ALLOWED_SCHEME = "http";
    private static final String ALLOWED_HOST = "192.168.1.64";
    private static final int ALLOWED_PORT = 18091;
    private static final long NFC_DEBOUNCE_MS = 1500L;

    private WebView webView;
    private NfcAdapter nfcAdapter;
    private boolean pageReady = false;
    private String pendingNfcEvent = null;
    private String lastUid = null;
    private long lastScanElapsedMs = 0L;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        webView = new WebView(this);
        webView.setBackgroundColor(Color.BLACK);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setUserAgentString(
                settings.getUserAgentString() + " WorkshopVentilationHmi/0.1"
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

        // The iiyama Android 13 firmware may not have a DecorView-backed
        // WindowInsetsController available at the beginning of onCreate().
        // Defer immersive-mode setup until the content view is attached.
        scheduleImmersiveMode();

        nfcAdapter = NfcAdapter.getDefaultAdapter(this);
        webView.loadUrl(HMI_URL);
    }

    private boolean isAllowedUri(Uri uri) {
        if (uri == null) {
            return false;
        }

        return ALLOWED_SCHEME.equalsIgnoreCase(uri.getScheme())
                && ALLOWED_HOST.equals(uri.getHost())
                && uri.getPort() == ALLOWED_PORT;
    }

    @Override
    protected void onResume() {
        super.onResume();
        scheduleImmersiveMode();

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

        if (hasFocus) {
            scheduleImmersiveMode();
        }
    }

    @Override
    public void onTagDiscovered(Tag tag) {
        byte[] rawUid = tag.getId();
        String uid = toHexCompact(rawUid);

        if (uid.isEmpty() || isDebounced(uid)) {
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
        // Intentional: the production HMI must not leave the kiosk surface via BACK.
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
