package pl.autoklinika.workshopventilation.hmi;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;
import java.util.Set;

/**
 * Local credentials used only for leaving Android Lock Task Mode on the dedicated HMI.
 *
 * The service PIN is stored as a salted SHA-256 digest rather than plaintext. The NFC
 * allowlist contains compact hexadecimal tag UIDs. Both values are intentionally empty
 * until the physical service card and final service PIN are selected during Stage 3.
 */
final class ServiceAccessConfig {

    private static final String SERVICE_PIN_SALT = "wvc-iiyama-service-exit-v1";
    private static final String SERVICE_PIN_SHA256 = "";

    private static final Set<String> SERVICE_NFC_UIDS = Set.of();

    private ServiceAccessConfig() {
    }

    static boolean isPinConfigured() {
        return !SERVICE_PIN_SHA256.isEmpty();
    }

    static boolean matchesPin(String pin) {
        if (!isPinConfigured() || pin == null) {
            return false;
        }

        String candidate = sha256Hex(SERVICE_PIN_SALT + ":" + pin);
        return MessageDigest.isEqual(
                candidate.getBytes(StandardCharsets.US_ASCII),
                SERVICE_PIN_SHA256.getBytes(StandardCharsets.US_ASCII)
        );
    }

    static boolean isServiceCard(String uid) {
        if (uid == null || uid.isEmpty()) {
            return false;
        }
        return SERVICE_NFC_UIDS.contains(normalizeUid(uid));
    }

    static String normalizeUid(String uid) {
        return uid.replace(" ", "")
                .replace(":", "")
                .replace("-", "")
                .trim()
                .toUpperCase(Locale.US);
    }

    private static String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder(bytes.length * 2);
            for (byte item : bytes) {
                out.append(String.format(Locale.US, "%02x", item & 0xFF));
            }
            return out.toString();
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }
}
