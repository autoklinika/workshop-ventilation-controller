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
     * Hardware-validated commands from the original HMI bring-up / VS Code tasks.
     * These are COMMANDS, not a linear RGB palette.
     */
    static final int CMD_BRIGHTNESS_UP = 0x00;
    static final int CMD_BRIGHTNESS_DOWN = 0x01;
    static final int CMD_OFF = 0x02;
    static final int CMD_ON = 0x03;
    static final int CMD_RED = 0x04;
    static final int CMD_GREEN = 0x05;
    static final int CMD_BLUE = 0x06;
    static final int CMD_WHITE = 0x07;

    /*
     * Previously observed effect commands. They are intentionally never used by
     * alert presentation because they animate/change colours by themselves.
     * 0x0B = colour cycle
     * 0x0F = white dim/bright effect
     * 0x13 = dim/bright with colour change
     * 0x17 = green/blue/red loop
     */
    private static final int EFFECT_COLOR_CYCLE_0B = 0x0B;
    private static final int EFFECT_WHITE_DIM_0F = 0x0F;
    private static final int EFFECT_DIM_COLOR_CHANGE_13 = 0x13;
    private static final int EFFECT_RGB_LOOP_17 = 0x17;

    // Until a real static yellow/orange command is identified, never use an effect as a colour.
    static final int CMD_WARNING = CMD_RED;
    static final int CMD_ALARM = CMD_RED;

    private boolean ledEnabled = false;

    /**
     * Mirrors the command model that was validated manually on the panel:
     *
     *   direct colour: echo w 0x04..0x07 > ... | su
     *   off:           echo w 0x02 > ... | su
     *   after OFF:     ON (0x03) first, then the selected static colour
     *
     * Crucially, 0x03 is NOT sent before every colour change and no 0x08..0x17
     * effect command is ever used as a static alert colour.
     */
    synchronized boolean writeCommand(int command) {
        if (command == CMD_OFF) {
            boolean ok = executeRootCommands(CMD_OFF);
            if (ok) {
                ledEnabled = false;
            }
            return ok;
        }

        if (!isStaticColour(command)) {
            Log.e(TAG, "Rejected non-static RGB command 0x"
                    + String.format(Locale.US, "%02X", command));
            return false;
        }

        boolean ok;
        if (ledEnabled) {
            ok = executeRootCommands(command);
        } else {
            ok = executeRootCommands(CMD_ON, command);
        }

        if (ok) {
            ledEnabled = true;
        }
        return ok;
    }

    private static boolean isStaticColour(int command) {
        return command == CMD_RED
                || command == CMD_GREEN
                || command == CMD_BLUE
                || command == CMD_WHITE;
    }

    private boolean executeRootCommands(int... commands) {
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

            StringBuilder codes = new StringBuilder();
            for (int command : commands) {
                if (codes.length() > 0) {
                    codes.append(',');
                }
                codes.append(String.format(Locale.US, "0x%02X", command & 0xFF));
            }
            Log.i(TAG, "RGB write PASS commands=" + codes);
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
