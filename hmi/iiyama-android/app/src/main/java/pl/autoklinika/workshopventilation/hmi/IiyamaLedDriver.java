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
    private static final long ON_SETTLE_MS = 200L;

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
     * Drive the vendor sysfs through a one-shot interactive `su` session.
     *
     * This deliberately mirrors the command path validated manually on the panel:
     *   printf 'echo ...\nexit\n' | su
     *
     * `su -c` is not used because this iiyama firmware does not execute that form
     * reliably from the application process.
     */
    synchronized boolean writeCode(int code) {
        Process process = null;
        try {
            process = new ProcessBuilder("su")
                    .redirectErrorStream(true)
                    .start();

            try (BufferedWriter input = new BufferedWriter(new OutputStreamWriter(
                    process.getOutputStream(), StandardCharsets.UTF_8))) {
                if (code == CODE_OFF) {
                    writeRawCode(input, CODE_OFF);
                } else {
                    writeRawCode(input, CODE_ON);
                    input.flush();
                    waitForOnSettle();
                    writeRawCode(input, code);
                }
                input.write("exit");
                input.newLine();
                input.flush();
            }

            boolean finished = process.waitFor(COMMAND_TIMEOUT_MS, TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                Log.e(TAG, "Timed out writing iiyama RGB code 0x"
                        + String.format(Locale.US, "%02X", code));
                return false;
            }

            int exit = process.exitValue();
            if (exit != 0) {
                Log.e(TAG, "iiyama RGB command failed exit=" + exit + " code=0x"
                        + String.format(Locale.US, "%02X", code));
                return false;
            }

            Log.i(TAG, "RGB write PASS code=0x" + String.format(Locale.US, "%02X", code));
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

    private static void writeRawCode(BufferedWriter input, int code) throws IOException {
        input.write(String.format(Locale.US, "echo w 0x%02X > %s", code & 0xFF, SYSFS));
        input.newLine();
    }

    private static void waitForOnSettle() throws IOException {
        try {
            Thread.sleep(ON_SETTLE_MS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IOException("Interrupted while enabling iiyama RGB bar", error);
        }
    }
}
