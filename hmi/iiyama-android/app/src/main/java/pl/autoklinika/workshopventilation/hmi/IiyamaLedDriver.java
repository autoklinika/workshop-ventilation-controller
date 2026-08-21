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
     * Important B3 behaviour, confirmed with the Android renderer PAUSED so
     * manual ADB -> su was the only LED writer:
     * - 0x02 latches the bar OFF;
     * - after that OFF latch, a colour command by itself does not reliably
     *   restore the requested colour;
     * - 0x03 wakes the bar (default white), and the requested colour must follow
     *   immediately in the SAME su session: 0x03 + COLOR.
     */
    static final int CMD_UNKNOWN_00 = 0x00;
    static final int CMD_UNKNOWN_01 = 0x01;
    static final int CMD_OFF = 0x02;
    static final int CMD_ON = 0x03;
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
     * Applies one logical LED command.
     *
     * OFF is one vendor write: 0x02.
     * Any visible static colour is re-armed atomically as 0x03 + COLOR in one
     * root shell. The controller's lastAppliedCommand still prevents redundant
     * physical writes while a state is steady.
     */
    synchronized boolean writeCommand(int command) {
        if (command == CMD_OFF) {
            return executeRootSequence(CMD_OFF);
        }
        if (!isStaticColour(command)) {
            Log.e(TAG, "Rejected non-static RGB command 0x"
                    + String.format(Locale.US, "%02X", command));
            return false;
        }
        return executeRootSequence(CMD_ON, command);
    }

    private static boolean isStaticColour(int command) {
        return command == CMD_RED
                || command == CMD_GREEN
                || command == CMD_BLUE
                || command == CMD_WHITE
                || command == CMD_ORANGE
                || command == CMD_YELLOW;
    }

    private boolean executeRootSequence(int... commands) {
        Process process = null;
        try {
            process = new ProcessBuilder("su")
                    .redirectErrorStream(true)
                    .start();

            try (BufferedWriter input = new BufferedWriter(new OutputStreamWriter(
                    process.getOutputStream(), StandardCharsets.UTF_8))) {
                for (int command : commands) {
                    input.write(String.format(Locale.US,
                            "echo w 0x%02X > %s", command & 0xFF, SYSFS));
                    input.newLine();
                }
                input.write("exit");
                input.newLine();
                input.flush();
            }

            boolean finished = process.waitFor(COMMAND_TIMEOUT_MS, TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                Log.e(TAG, "Timed out writing iiyama RGB command sequence");
                return false;
            }

            if (process.exitValue() != 0) {
                Log.e(TAG, "iiyama RGB command sequence failed exit=" + process.exitValue());
                return false;
            }

            StringBuilder sequence = new StringBuilder();
            for (int index = 0; index < commands.length; index++) {
                if (index > 0) {
                    sequence.append(',');
                }
                sequence.append(String.format(Locale.US, "0x%02X", commands[index] & 0xFF));
            }
            Log.i(TAG, "RGB write PASS commands=" + sequence);
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
