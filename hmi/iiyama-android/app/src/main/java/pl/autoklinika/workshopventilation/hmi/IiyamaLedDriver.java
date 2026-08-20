package pl.autoklinika.workshopventilation.hmi;

import android.util.Log;

import java.io.IOException;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/** Low-level iiyama TW1025LASC-B3PNR RGB bar driver. */
final class IiyamaLedDriver {

    private static final String TAG = "WvcHmiLed";
    private static final String SYSFS = "/sys/devices/platform/led_con_h/zigbee_reset";
    private static final long COMMAND_TIMEOUT_MS = 1200L;

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

    /**
     * Execute every vendor transition as one atomic root-shell transaction.
     *
     * The panel expects COLOR to be preceded by LED ON. Keeping a long-lived shell and
     * splitting ON/COLOR into separate writes proved unreliable on real hardware after
     * an ACK transition: the vendor LED engine could remain in its colour-cycle mode.
     *
     * Therefore:
     *   OFF   -> one command containing only 0x02
     *   COLOR -> one `su -c` command containing `0x03 && COLOR`
     *
     * This matches the hardware command sequence validated manually on the iiyama.
     */
    synchronized boolean writeCode(int code) {
        String command;
        if (code == CODE_OFF) {
            command = rawCommand(CODE_OFF);
        } else {
            command = rawCommand(CODE_ON) + " && " + rawCommand(code);
        }

        Process process = null;
        try {
            process = new ProcessBuilder("su", "-c", command)
                    .redirectErrorStream(true)
                    .start();

            boolean finished = process.waitFor(COMMAND_TIMEOUT_MS, TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                Log.e(TAG, "Timed out writing iiyama RGB code 0x" + String.format(Locale.US, "%02X", code));
                return false;
            }

            int exit = process.exitValue();
            if (exit != 0) {
                Log.e(TAG, "iiyama RGB command failed exit=" + exit + " code=0x"
                        + String.format(Locale.US, "%02X", code));
                return false;
            }

            Log.d(TAG, "RGB write code=0x" + String.format(Locale.US, "%02X", code));
            return true;
        } catch (IOException error) {
            Log.e(TAG, "Unable to start root command for iiyama RGB bar", error);
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

    private static String rawCommand(int code) {
        return String.format(Locale.US, "echo w 0x%02X > %s", code & 0xFF, SYSFS);
    }
}
