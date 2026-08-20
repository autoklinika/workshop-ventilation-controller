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

    // Hardware-validated vendor commands.
    static final int CODE_OFF = 0x02;
    static final int CODE_RED = 0x04;
    static final int CODE_GREEN = 0x05;
    static final int CODE_BLUE = 0x06;
    static final int CODE_WHITE = 0x07;

    // 0x08..0x17 are additional vendor palette colors, but yellow/orange have not yet
    // been identified on this exact panel. Until hardware palette calibration is done,
    // WARNING/ALARM fail conspicuously to red instead of guessing an unverified code.
    static final int CODE_WARNING_FALLBACK = CODE_RED;
    static final int CODE_ALARM_FALLBACK = CODE_RED;

    private Process rootShell;
    private BufferedWriter rootInput;

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
        String command = String.format(Locale.US, "echo w 0x%02X > %s", code & 0xFF, SYSFS);
        rootInput.write(command);
        rootInput.newLine();
        rootInput.flush();
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
        Log.i(TAG, "Persistent root shell opened for iiyama RGB bar");
    }

    private void closeRootShell() {
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
