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
 *   has priority and is shown as red blink;
 * - highest active alert priority wins;
 * - ACK never lowers alert priority or changes its presentation colour; it only changes
 *   the local LED pattern from blinking to solid;
 * - local service / Android mode is blue only when there is no active alert.
 */
final class HmiLedController {

    private static final String TAG = "WvcHmiLed";
    private static final String ALERTS_URL = "http://192.168.1.64:18091/api/v1/alerts";
    private static final long POLL_INTERVAL_MS = 2000L;
    private static final long COMMUNICATION_STALE_MS = 6000L;
    private static final long LED_TICK_MS = 250L;

    /* Temporary hardware-test value. Production timing will be finalized only
     * after the B3 OFF/re-arm sequence is validated without competing writers. */
    private static final long RED_BLINK_HALF_PERIOD_MS = 500L;

    private final ScheduledExecutorService executor = Executors.newScheduledThreadPool(2, runnable -> {
        Thread thread = new Thread(runnable, "wvc-hmi-led");
        thread.setDaemon(true);
        return thread;
    });
    private final IiyamaLedDriver driver = new IiyamaLedDriver();
    private final Object renderLock = new Object();

    private volatile LedState state = LedState.STARTUP_UNKNOWN;
    private volatile boolean localServiceMode = false;
    private volatile boolean everConnected = false;
    private volatile long lastSuccessfulPollElapsedMs = 0L;
    private volatile long stateChangedElapsedMs = SystemClock.elapsedRealtime();
    private volatile int lastAppliedCommand = -1;

    private volatile LedState diagnosticOverride = null;
    private volatile long diagnosticChangedElapsedMs = SystemClock.elapsedRealtime();
    private volatile boolean diagnosticRendererPaused = false;

    void start() {
        executor.scheduleWithFixedDelay(this::pollAlertsSafely, 0L, POLL_INTERVAL_MS, TimeUnit.MILLISECONDS);
        executor.scheduleAtFixedRate(this::renderLedSafely, 0L, LED_TICK_MS, TimeUnit.MILLISECONDS);
        Log.i(TAG, "Android alert LED controller started; direct core polling enabled");
    }

    void setLocalServiceMode(boolean enabled) {
        localServiceMode = enabled;
        if (everConnected && state == LedState.NORMAL && enabled) {
            setState(LedState.SERVICE);
        } else if (everConnected && state == LedState.SERVICE && !enabled) {
            setState(LedState.NORMAL);
        }
    }

    /** Debug-only caller entry point used by HmiApplication's ADB diagnostic receiver. */
    boolean setDiagnosticOverride(String requestedState) {
        String normalized = requestedState == null
                ? ""
                : requestedState.trim().toUpperCase(Locale.ROOT);

        synchronized (renderLock) {
            if ("PAUSE".equals(normalized)) {
                diagnosticRendererPaused = true;
                diagnosticOverride = null;
                lastAppliedCommand = -1;
                Log.i(TAG, "LED DIAGNOSTIC renderer PAUSED; live polling continues, physical writes disabled");
                return true;
            }

            if ("CLEAR".equals(normalized)) {
                LedState previous = diagnosticOverride;
                boolean wasPaused = diagnosticRendererPaused;
                diagnosticRendererPaused = false;
                diagnosticOverride = null;
                stateChangedElapsedMs = SystemClock.elapsedRealtime();
                lastAppliedCommand = -1;
                Log.i(TAG, "LED DIAGNOSTIC cleared; previousOverride=" + previous
                        + ", rendererWasPaused=" + wasPaused + ", live=" + state);
                return true;
            }

            try {
                LedState next = LedState.valueOf(normalized);
                diagnosticRendererPaused = false;
                diagnosticOverride = next;
                diagnosticChangedElapsedMs = SystemClock.elapsedRealtime();
                lastAppliedCommand = -1;
                Log.i(TAG, "LED DIAGNOSTIC override -> " + next);
                return true;
            } catch (IllegalArgumentException error) {
                Log.w(TAG, "LED DIAGNOSTIC rejected unknown state: " + requestedState);
                return false;
            }
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
                return 2;
        }
    }

    private void setState(LedState next) {
        synchronized (renderLock) {
            LedState previous = state;
            if (previous == next) {
                return;
            }
            state = next;
            stateChangedElapsedMs = SystemClock.elapsedRealtime();
            if (diagnosticOverride == null && !diagnosticRendererPaused) {
                lastAppliedCommand = -1;
            }
            Log.i(TAG, "LED state: " + previous + " -> " + next);
        }
    }

    private void renderLedSafely() {
        try {
            synchronized (renderLock) {
                if (diagnosticRendererPaused) {
                    return;
                }

                LedState override = diagnosticOverride;
                LedState current = override != null ? override : state;
                long phaseStartedMs = override != null
                        ? diagnosticChangedElapsedMs
                        : stateChangedElapsedMs;
                long ageMs = Math.max(0L, SystemClock.elapsedRealtime() - phaseStartedMs);
                boolean on = current.isSolid() || ((ageMs / current.blinkHalfPeriodMs) % 2L == 0L);
                int command = on ? current.staticColourCommand : IiyamaLedDriver.CMD_OFF;
                if (command == lastAppliedCommand) {
                    return;
                }
                Log.i(TAG, "LED render state=" + current + " command=0x"
                        + String.format(Locale.US, "%02X", command & 0xFF));
                if (driver.writeCommand(command)) {
                    lastAppliedCommand = command;
                }
            }
        } catch (RuntimeException error) {
            Log.e(TAG, "Unable to render RGB LED state", error);
        }
    }

    enum LedState {
        STARTUP_UNKNOWN(IiyamaLedDriver.CMD_WHITE, 1000L),
        COMMUNICATION_LOST(IiyamaLedDriver.CMD_RED, RED_BLINK_HALF_PERIOD_MS),
        NORMAL(IiyamaLedDriver.CMD_GREEN, 0L),
        SERVICE(IiyamaLedDriver.CMD_BLUE, 0L),
        INFO_ACK(IiyamaLedDriver.CMD_BLUE, 0L),
        INFO_UNACK(IiyamaLedDriver.CMD_BLUE, 1500L),
        WARNING_ACK(IiyamaLedDriver.CMD_YELLOW, 0L),
        WARNING_UNACK(IiyamaLedDriver.CMD_YELLOW, 1000L),
        ALARM_ACK(IiyamaLedDriver.CMD_ORANGE, 0L),
        ALARM_UNACK(IiyamaLedDriver.CMD_ORANGE, 500L),
        CRITICAL_ACK(IiyamaLedDriver.CMD_RED, 0L),
        CRITICAL_UNACK(IiyamaLedDriver.CMD_RED, RED_BLINK_HALF_PERIOD_MS);

        final int staticColourCommand;
        final long blinkHalfPeriodMs;

        LedState(int staticColourCommand, long blinkHalfPeriodMs) {
            this.staticColourCommand = staticColourCommand;
            this.blinkHalfPeriodMs = blinkHalfPeriodMs;
        }

        boolean isSolid() {
            return blinkHalfPeriodMs <= 0L;
        }
    }
}
