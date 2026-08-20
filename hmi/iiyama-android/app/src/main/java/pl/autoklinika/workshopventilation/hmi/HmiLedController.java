package pl.autoklinika.workshopventilation.hmi;

import android.os.SystemClock;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Resolves the HMI RGB status from the existing ventilation-core alert API.
 *
 * Safety / architecture rules:
 * - ventilation-core remains the source of truth for alerts;
 * - this class never creates or clears an alert and never affects ventilation control;
 * - startup before the first valid snapshot is UNKNOWN (white blink);
 * - after a previously healthy connection becomes stale, local HMI communication loss
 *   has priority and is shown as red fast blink;
 * - highest active alert priority wins;
 * - ACK never lowers alert priority or changes its color; it only changes the local LED
 *   pattern from blinking to solid;
 * - local service / Android mode is blue only when there is no active alert.
 */
final class HmiLedController {

    private static final String TAG = "WvcHmiLed";
    private static final String ALERTS_URL = "http://192.168.1.64:18091/api/v1/alerts";
    private static final long POLL_INTERVAL_MS = 2000L;
    private static final long COMMUNICATION_STALE_MS = 6000L;
    private static final long LED_TICK_MS = 250L;

    private final ScheduledExecutorService executor = Executors.newScheduledThreadPool(2, runnable -> {
        Thread thread = new Thread(runnable, "wvc-hmi-led");
        thread.setDaemon(true);
        return thread;
    });
    private final IiyamaLedDriver driver = new IiyamaLedDriver();

    private volatile LedState state = LedState.STARTUP_UNKNOWN;
    private volatile boolean localServiceMode = false;
    private volatile boolean everConnected = false;
    private volatile long lastSuccessfulPollElapsedMs = 0L;
    private volatile long stateChangedElapsedMs = SystemClock.elapsedRealtime();
    private volatile int lastAppliedCode = -1;

    void start() {
        executor.scheduleWithFixedDelay(this::pollAlertsSafely, 0L, POLL_INTERVAL_MS, TimeUnit.MILLISECONDS);
        executor.scheduleAtFixedRate(this::renderLedSafely, 0L, LED_TICK_MS, TimeUnit.MILLISECONDS);
        Log.i(TAG, "Android alert LED controller started; direct core polling enabled");
    }

    void setLocalServiceMode(boolean enabled) {
        localServiceMode = enabled;
        // Re-resolve immediately from the last successful transport state on next poll.
        // Between polls, no alert is downgraded; service mode only affects an otherwise normal state.
        if (everConnected && state == LedState.NORMAL && enabled) {
            setState(LedState.SERVICE);
        } else if (everConnected && state == LedState.SERVICE && !enabled) {
            setState(LedState.NORMAL);
        }
    }

    private void pollAlertsSafely() {
        try {
            JSONObject payload = fetchAlertSnapshot();
            if (!payload.optBoolean("ok", false)) {
                throw new IllegalStateException("core alert API returned ok=false");
            }
            JSONArray active = payload.optJSONArray("active");
            if (active == null) {
                throw new IllegalStateException("core alert API has no active array");
            }

            everConnected = true;
            lastSuccessfulPollElapsedMs = SystemClock.elapsedRealtime();
            setState(resolveActiveAlerts(active, localServiceMode));
        } catch (Exception error) {
            long now = SystemClock.elapsedRealtime();
            if (!everConnected) {
                setState(LedState.STARTUP_UNKNOWN);
            } else if (now - lastSuccessfulPollElapsedMs >= COMMUNICATION_STALE_MS) {
                setState(LedState.COMMUNICATION_LOST);
            }
            Log.w(TAG, "Alert LED poll failed: " + String.valueOf(error.getMessage()));
        }
    }

    private JSONObject fetchAlertSnapshot() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(ALERTS_URL).openConnection();
        connection.setRequestMethod("GET");
        connection.setConnectTimeout(1500);
        connection.setReadTimeout(1500);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("User-Agent", "WorkshopVentilationHmiLed/1.0");

        int status = connection.getResponseCode();
        if (status < 200 || status >= 300) {
            connection.disconnect();
            throw new IllegalStateException("HTTP " + status);
        }

        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line);
            }
        } finally {
            connection.disconnect();
        }
        return new JSONObject(body.toString());
    }

    static LedState resolveActiveAlerts(JSONArray active, boolean serviceMode) {
        int highestWeight = 0;
        boolean unacknowledgedAtHighestWeight = false;

        for (int index = 0; index < active.length(); index++) {
            JSONObject alert = active.optJSONObject(index);
            if (alert == null || !alert.optBoolean("active", false)) {
                continue;
            }

            int weight = resolveWeight(alert);
            boolean unacknowledged = !alert.optBoolean("acknowledged", false);
            if (weight > highestWeight) {
                highestWeight = weight;
                unacknowledgedAtHighestWeight = unacknowledged;
            } else if (weight == highestWeight && unacknowledged) {
                unacknowledgedAtHighestWeight = true;
            }
        }

        if (highestWeight >= 4) {
            return unacknowledgedAtHighestWeight ? LedState.CRITICAL_UNACK : LedState.CRITICAL_ACK;
        }
        if (highestWeight == 3) {
            return unacknowledgedAtHighestWeight ? LedState.ALARM_UNACK : LedState.ALARM_ACK;
        }
        if (highestWeight == 2) {
            return unacknowledgedAtHighestWeight ? LedState.WARNING_UNACK : LedState.WARNING_ACK;
        }
        if (highestWeight == 1) {
            return unacknowledgedAtHighestWeight ? LedState.INFO_UNACK : LedState.INFO_ACK;
        }
        return serviceMode ? LedState.SERVICE : LedState.NORMAL;
    }

    private static int resolveWeight(JSONObject alert) {
        if (alert.has("weight")) {
            int weight = alert.optInt("weight", -1);
            if (weight >= 0 && weight <= 4) {
                return weight;
            }
        }

        String severity = alert.optString("severity", "").trim().toLowerCase(Locale.ROOT);
        switch (severity) {
            case "critical":
                return 4;
            case "alarm":
                return 3;
            case "warning":
                return 2;
            case "info":
                return 1;
            default:
                // Current production API uses warning/critical. An unknown active severity
                // is not treated as NORMAL; conservatively surface it as WARNING.
                return 2;
        }
    }

    private void setState(LedState next) {
        LedState previous = state;
        if (previous == next) {
            return;
        }
        state = next;
        stateChangedElapsedMs = SystemClock.elapsedRealtime();
        lastAppliedCode = -1;
        Log.i(TAG, "LED state: " + previous + " -> " + next);
    }

    private void renderLedSafely() {
        try {
            LedState current = state;
            long ageMs = Math.max(0L, SystemClock.elapsedRealtime() - stateChangedElapsedMs);
            boolean on = current.isSolid() || ((ageMs / current.blinkHalfPeriodMs) % 2L == 0L);
            int code = on ? current.colorCode : IiyamaLedDriver.CODE_OFF;
            if (code == lastAppliedCode) {
                return;
            }
            if (driver.writeCode(code)) {
                lastAppliedCode = code;
            }
        } catch (RuntimeException error) {
            Log.e(TAG, "Unable to render RGB LED state", error);
        }
    }

    enum LedState {
        STARTUP_UNKNOWN(IiyamaLedDriver.CODE_WHITE, 1000L),
        COMMUNICATION_LOST(IiyamaLedDriver.CODE_RED, 250L),
        NORMAL(IiyamaLedDriver.CODE_GREEN, 0L),
        SERVICE(IiyamaLedDriver.CODE_BLUE, 0L),
        INFO_ACK(IiyamaLedDriver.CODE_BLUE, 0L),
        INFO_UNACK(IiyamaLedDriver.CODE_BLUE, 1500L),
        WARNING_ACK(IiyamaLedDriver.CODE_WARNING_FALLBACK, 0L),
        WARNING_UNACK(IiyamaLedDriver.CODE_WARNING_FALLBACK, 1000L),
        ALARM_ACK(IiyamaLedDriver.CODE_ALARM_FALLBACK, 0L),
        ALARM_UNACK(IiyamaLedDriver.CODE_ALARM_FALLBACK, 500L),
        CRITICAL_ACK(IiyamaLedDriver.CODE_RED, 0L),
        CRITICAL_UNACK(IiyamaLedDriver.CODE_RED, 250L);

        final int colorCode;
        final long blinkHalfPeriodMs;

        LedState(int colorCode, long blinkHalfPeriodMs) {
            this.colorCode = colorCode;
            this.blinkHalfPeriodMs = blinkHalfPeriodMs;
        }

        boolean isSolid() {
            return blinkHalfPeriodMs <= 0L;
        }
    }
}
