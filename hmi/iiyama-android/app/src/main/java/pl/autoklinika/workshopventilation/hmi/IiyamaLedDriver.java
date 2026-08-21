package pl.autoklinika.workshopventilation.hmi;

import android.util.Log;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/** Low-level iiyama TW1025LASC-B3PNR RGB bar driver. */
final class IiyamaLedDriver {

    private static final String TAG = "WvcHmiLed";
    private static final String SYSFS = "/sys/devices/platform/led_con_h/zigbee_reset";
    private static final long COMMAND_TIMEOUT_MS = 1500L;

    /*
     * Hardware-validated vendor commands on the target B3 panel.
     * These are command/function codes, not a linear RGB value space.
     *
     * Important: the original known-good VS Code tasks wrote exactly ONE value
     * for RED/GREEN/BLUE/WHITE/OFF. They did not prepend 0x03 before a colour.
     * Stage 1 therefore mirrors that proven hardware contract exactly.
     */
    static final int CMD_UNKNOWN_00 = 0x00;
    static final int CMD_UNKNOWN_01 = 0x01;
    static final int CMD_OFF = 0x02;
    static final int CMD_ON = 0x03; // documented/observed, intentionally unused by alert rendering
    static final int CMD_RED = 0x04;
    static final int CMD_GREEN = 0x05;
    static final int CMD_BLUE = 0x06;
    static final int CMD_WHITE = 0x07;
    static final int CMD_ORANGE = 0x08;
    static final int CMD_YELLOW = 0x10;

    /*
     * Hardware-validated animated/effect commands. They are intentionally not
     * used for alert presentation because each effect owns its colour behavior.
     */
    static final int EFFECT_COLOR_SEQUENCE = 0x0B;
    static final int EFFECT_WHITE_FADE = 0x0F;
    static final int EFFECT_MULTICOLOR_FADE = 0x13;
    static final int EFFECT_COLOR_STEP = 0x17;

    /**
     * Writes exactly one hardware command per requested state change.
     *
     * This deliberately avoids the previous OFF -> 0x03 -> colour sequence.
     * The diagnostic logs showed that sequence was generated correctly by Android,
     * but it was not the command pattern used by the original hardware-proven tasks.
     * Keeping every transition atomic also removes one possible source of controller
     * side effects and halves the write rate while blinking.
     */
    synchronized boolean writeCommand(int command) {
        if (command != CMD_OFF && !isStaticColour(command)) {
            Log.e(TAG, "Rejected non-static RGB command 0x"
                    + String.format(Locale.US, "%02X", command));
            return false;
        }
        return executeRootCommand(command);
    }

    private static boolean isStaticColour(int command) {
        return command == CMD_RED
                || command == CMD_GREEN
                || command == CMD_BLUE
                || command == CMD_WHITE
                || command == CMD_ORANGE
                || command == CMD_YELLOW;
    }

    private boolean executeRootCommand(int command) {
        Process process = null;
        try {
            process = new ProcessBuilder("su")
                    .redirectErrorStream(true)
                    .start();

            try (BufferedWriter input = new BufferedWriter(new OutputStreamWriter(
                    process.getOutputStream(), StandardCharsets.UTF_8))) {
                input.write(String.format(Locale.US,
                        "echo w 0x%02X > %s", command & 0xFF, SYSFS));
                input.newLine();
                input.write("exit");
                input.newLine();
                input.flush();
            }

            boolean finished = process.waitFor(COMMAND_TIMEOUT_MS, TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                Log.e(TAG, "Timed out writing iiyama RGB command");
                return false;
            }

            if (process.exitValue() != 0) {
                Log.e(TAG, "iiyama RGB command failed exit=" + process.exitValue());
                return false;
            }

            Log.i(TAG, "RGB write PASS command="
                    + String.format(Locale.US, "0x%02X", command & 0xFF));
            return true;
        } catch (IOException error) {
            Log.e(TAG, "Unable to use root shell for iiyama RGB bar", error);
            return false;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            Log.e(TAG, "Interrupted while writing iiyama RGB bar", error);
            return false;
        } finally {
            if (process != null) {
                process.destroy();
            }
        }
    }
}
