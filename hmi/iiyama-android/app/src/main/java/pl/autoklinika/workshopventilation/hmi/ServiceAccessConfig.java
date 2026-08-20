package pl.autoklinika.workshopventilation.hmi;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.Collections;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

/** Local service-exit credentials for the dedicated HMI. */
final class ServiceAccessConfig {

    private static final String SERVICE_PIN_SALT = "wvc-iiyama-service-exit-v1";

    private static final Set<String> SERVICE_NFC_UIDS = parseUidSet(
            BuildConfig.SERVICE_NFC_UIDS
    );

    private ServiceAccessConfig() {
    }

    static boolean isPinConfigured() {
        return BuildConfig.SERVICE_PIN_SHA256 != null
                && !BuildConfig.SERVICE_PIN_SHA256.isEmpty();
    }

    static boolean matchesPin(String pin) {
        if (!isPinConfigured() || pin == null) {
            return false;
        }

        String candidate = sha256Hex(SERVICE_PIN_SALT + ":" + pin);
        return MessageDigest.isEqual(
                candidate.getBytes(StandardCharsets.US_ASCII),
                BuildConfig.SERVICE_PIN_SHA256.getBytes(StandardCharsets.US_ASCII)
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

    private static Set<String> parseUidSet(String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            return Collections.emptySet();
        }

        return Arrays.stream(raw.split(","))
                .map(ServiceAccessConfig::normalizeUid)
                .filter(value -> !value.isEmpty())
                .collect(Collectors.toUnmodifiableSet());
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
