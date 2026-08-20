package pl.autoklinika.workshopventilation.hmi;

import java.util.Locale;

/** Shared service-access normalization helpers. */
final class ServiceAccessConfig {

    private ServiceAccessConfig() {
    }

    static String normalizeUid(String uid) {
        if (uid == null) {
            return "";
        }
        return uid.replace(" ", "")
                .replace(":", "")
                .replace("-", "")
                .trim()
                .toUpperCase(Locale.US);
    }
}
