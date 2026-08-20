package pl.autoklinika.workshopventilation.hmi;

import android.util.Log;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/** Low-level iiyama TW1025LASC-B3PNR RGB bar driver. */
final class IiyamaLedDriver {

    private static final String TAG = "WvcHmiLed";
    private static final String SYSFS = "/sys/devices/platform/led_con_h/zigbee_reset";
    private static final long ENABLE_SETTLE_MS = 100L;

    // Hardware-validated vendor commands.
    static final int CODE_OFF = 0x02;
    static final int CODE_ON = 0x03;
    static final int CODE_RED = 0x04;
    static final int CODE_GREEN = 0x05;
    static final int CODE_BLUE = 0x06;
    static final int CODE_WHITE = 0x07;
    static final int CODE_ORANGE = 0x08;
    static final int CODE_YELLOW = 0x0B;

    static final int CODE_WARNING_FALLBACK = CODE_YELLOW;
    static final int CODE_ALARM_FALLBACK = CODE_ORANGE;

    private Process rootShell;
    private BufferedWriter rootInput;
    private boolean ledEnabled = false;

    synchronized boolean writeCode(int code) {
        try {
            ensureRootShell();
            writeCommand(code);
            return true;
        } catch (IOException error) {
            Log.w(TAG, "LED root shell write failed; retrying once", error);
            closeRootShell();
            try {
                ensureRootShell();
                writeCommand(code);
                return true;
            } catch (IOException retryError) {
                Log.e(TAG, "LED root shell unavailable", retryError);
                closeRootShell();
                return false;
            }
        }
    }

    private void writeCommand(int code) throws IOException {
        if (code == CODE_OFF) {
            writeRawCode(CODE_OFF);
            ledEnabled = false;
            return;
        }

        // The vendor interface needs LED ON before a color is selected. Do this only
        // when the engine is actually off. Sending 0x03 before every command can leave
        // the panel in its vendor color-cycle mode if the following color write arrives
        // too quickly, which was observed during ACK transitions on real hardware.
        if (!ledEnabled) {
            writeRawCode(CODE_ON);
            waitForEnableSettle();
            ledEnabled = true;
        }

        writeRawCode(code);
    }

    private void writeRawCode(int code) throws IOException {
        String command = String.format(Locale.US, "echo w 0x%02X > %s", code & 0xFF, SYSFS);
        rootInput.write(command);
        rootInput.newLine();
        rootInput.flush();
    }

    private void waitForEnableSettle() throws IOException {
        try {
            Thread.sleep(ENABLE_SETTLE_MS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IOException("Interrupted while enabling iiyama RGB bar", error);
        }
    }

    private void ensureRootShell() throws IOException {
        if (rootShell != null && rootShell.isAlive() && rootInput != null) {
            return;
        }
        closeRootShell();
        rootShell = new ProcessBuilder("su")
                .redirectErrorStream(true)
                .start();
        rootInput = new BufferedWriter(new OutputStreamWriter(
                rootShell.getOutputStream(), StandardCharsets.UTF_8));
        ledEnabled = false;
        Log.i(TAG, "Persistent root shell opened for iiyama RGB bar");
    }

    private void closeRootShell() {
        ledEnabled = false;
        if (rootInput != null) {
            try {
                rootInput.close();
            } catch (IOException ignored) {
            }
            rootInput = null;
        }
        if (rootShell != null) {
            rootShell.destroy();
            rootShell = null;
        }
    }
}
