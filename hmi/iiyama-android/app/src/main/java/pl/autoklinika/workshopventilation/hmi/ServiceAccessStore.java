package pl.autoklinika.workshopventilation.hmi;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

/**
 * Persistent, app-private service access configuration.
 *
 * Card UIDs and labels are stored in private SharedPreferences. The service PIN is never
 * persisted in plaintext: it is verified using an HMAC-SHA256 key held by Android Keystore.
 * Stage 3 build-time credentials remain a one-way migration fallback so an already deployed
 * HMI does not lose its service access during the Stage 4 update.
 */
final class ServiceAccessStore {

    static final class CardEntry {
        final String uid;
        final String label;
        final long createdAtMs;
        final long lastUsedAtMs;

        CardEntry(String uid, String label, long createdAtMs, long lastUsedAtMs) {
            this.uid = uid;
            this.label = label;
            this.createdAtMs = createdAtMs;
            this.lastUsedAtMs = lastUsedAtMs;
        }
    }

    private static final String PREFS = "wvc_service_access_v1";
    private static final String KEY_CARDS_JSON = "cards_json";
    private static final String KEY_PIN_HMAC = "pin_hmac";
    private static final String KEY_LEGACY_CARDS_MIGRATED = "legacy_cards_migrated";
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String PIN_KEY_ALIAS = "wvc_service_pin_hmac_v1";
    private static final String LEGACY_PIN_SALT = "wvc-iiyama-service-exit-v1";

    private final SharedPreferences preferences;

    ServiceAccessStore(Context context) {
        preferences = context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        migrateLegacyCardsIfNeeded();
    }

    boolean isPinConfigured() {
        return !preferences.getString(KEY_PIN_HMAC, "").isEmpty()
                || (BuildConfig.SERVICE_PIN_SHA256 != null && !BuildConfig.SERVICE_PIN_SHA256.isEmpty());
    }

    boolean verifyPin(String pin) {
        if (pin == null || pin.isEmpty()) {
            return false;
        }

        String storedHmac = preferences.getString(KEY_PIN_HMAC, "");
        if (!storedHmac.isEmpty()) {
            byte[] expected;
            try {
                expected = Base64.decode(storedHmac, Base64.NO_WRAP);
            } catch (IllegalArgumentException error) {
                return false;
            }

            byte[] candidate = hmacPin(pin);
            return MessageDigest.isEqual(candidate, expected);
        }

        String legacyHash = BuildConfig.SERVICE_PIN_SHA256 == null
                ? ""
                : BuildConfig.SERVICE_PIN_SHA256.trim();
        if (legacyHash.isEmpty()) {
            return false;
        }

        String candidate = sha256Hex(LEGACY_PIN_SALT + ":" + pin);
        boolean valid = MessageDigest.isEqual(
                candidate.getBytes(StandardCharsets.US_ASCII),
                legacyHash.getBytes(StandardCharsets.US_ASCII)
        );

        if (valid) {
            // One-way migration: after the first valid Stage 3 PIN entry, Stage 4 stores
            // only the Keystore-backed HMAC value in private app storage.
            setPin(pin);
        }
        return valid;
    }

    void setPin(String pin) {
        if (pin == null || pin.trim().isEmpty()) {
            throw new IllegalArgumentException("PIN nie może być pusty");
        }
        String encoded = Base64.encodeToString(hmacPin(pin), Base64.NO_WRAP);
        preferences.edit().putString(KEY_PIN_HMAC, encoded).apply();
    }

    List<CardEntry> getCards() {
        List<CardEntry> cards = readCards();
        cards.sort(Comparator.comparing(card -> card.label.toLowerCase(Locale.US)));
        return cards;
    }

    boolean isServiceCard(String uid) {
        String normalized = ServiceAccessConfig.normalizeUid(uid);
        if (normalized.isEmpty()) {
            return false;
        }
        for (CardEntry card : readCards()) {
            if (card.uid.equals(normalized)) {
                return true;
            }
        }
        return false;
    }

    void addOrRenameCard(String uid, String label) {
        String normalized = ServiceAccessConfig.normalizeUid(uid);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Nieprawidłowy UID NFC");
        }

        String cleanLabel = label == null ? "" : label.trim();
        if (cleanLabel.isEmpty()) {
            cleanLabel = "Karta " + suffix(normalized);
        }

        List<CardEntry> cards = readCards();
        long now = System.currentTimeMillis();
        boolean replaced = false;
        for (int i = 0; i < cards.size(); i++) {
            CardEntry card = cards.get(i);
            if (card.uid.equals(normalized)) {
                cards.set(i, new CardEntry(card.uid, cleanLabel, card.createdAtMs, card.lastUsedAtMs));
                replaced = true;
                break;
            }
        }
        if (!replaced) {
            cards.add(new CardEntry(normalized, cleanLabel, now, 0L));
        }
        writeCards(cards);
    }

    boolean removeCard(String uid) {
        String normalized = ServiceAccessConfig.normalizeUid(uid);
        List<CardEntry> cards = readCards();
        boolean removed = cards.removeIf(card -> card.uid.equals(normalized));
        if (removed) {
            writeCards(cards);
        }
        return removed;
    }

    void recordCardUse(String uid) {
        String normalized = ServiceAccessConfig.normalizeUid(uid);
        List<CardEntry> cards = readCards();
        long now = System.currentTimeMillis();
        boolean changed = false;
        for (int i = 0; i < cards.size(); i++) {
            CardEntry card = cards.get(i);
            if (card.uid.equals(normalized)) {
                cards.set(i, new CardEntry(card.uid, card.label, card.createdAtMs, now));
                changed = true;
                break;
            }
        }
        if (changed) {
            writeCards(cards);
        }
    }

    private void migrateLegacyCardsIfNeeded() {
        if (preferences.getBoolean(KEY_LEGACY_CARDS_MIGRATED, false)) {
            return;
        }

        String raw = BuildConfig.SERVICE_NFC_UIDS == null ? "" : BuildConfig.SERVICE_NFC_UIDS.trim();
        if (raw.isEmpty()) {
            // Do not mark migration complete. A later local build may still carry the
            // Stage 3 bootstrap values from service-access.properties.
            return;
        }

        List<CardEntry> cards = readCards();
        long now = System.currentTimeMillis();
        int migrated = 0;

        for (String item : raw.split(",")) {
            String uid = ServiceAccessConfig.normalizeUid(item);
            if (uid.isEmpty()) {
                continue;
            }

            boolean exists = false;
            for (CardEntry card : cards) {
                if (card.uid.equals(uid)) {
                    exists = true;
                    break;
                }
            }
            if (!exists) {
                cards.add(new CardEntry(uid, "Karta Stage 3 " + suffix(uid), now, 0L));
                migrated++;
            }
        }

        if (migrated > 0) {
            writeCards(cards);
        }
        preferences.edit().putBoolean(KEY_LEGACY_CARDS_MIGRATED, true).apply();
    }

    private List<CardEntry> readCards() {
        List<CardEntry> cards = new ArrayList<>();
        String raw = preferences.getString(KEY_CARDS_JSON, "[]");
        try {
            JSONArray array = new JSONArray(raw);
            for (int i = 0; i < array.length(); i++) {
                JSONObject item = array.optJSONObject(i);
                if (item == null) {
                    continue;
                }
                String uid = ServiceAccessConfig.normalizeUid(item.optString("uid", ""));
                if (uid.isEmpty()) {
                    continue;
                }
                cards.add(new CardEntry(
                        uid,
                        item.optString("label", "Karta " + suffix(uid)),
                        item.optLong("created_at_ms", 0L),
                        item.optLong("last_used_at_ms", 0L)
                ));
            }
        } catch (Exception ignored) {
            // Corrupt local data must not crash the HMI. The user can re-add cards in service mode.
        }
        return cards;
    }

    private void writeCards(List<CardEntry> cards) {
        JSONArray array = new JSONArray();
        try {
            for (CardEntry card : cards) {
                JSONObject item = new JSONObject();
                item.put("uid", card.uid);
                item.put("label", card.label);
                item.put("created_at_ms", card.createdAtMs);
                item.put("last_used_at_ms", card.lastUsedAtMs);
                array.put(item);
            }
        } catch (Exception error) {
            throw new IllegalStateException("Nie udało się zapisać kart NFC", error);
        }
        preferences.edit().putString(KEY_CARDS_JSON, array.toString()).apply();
    }

    private byte[] hmacPin(String pin) {
        try {
            SecretKey key = getOrCreatePinKey();
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            return mac.doFinal(pin.getBytes(StandardCharsets.UTF_8));
        } catch (GeneralSecurityException | java.io.IOException error) {
            throw new IllegalStateException("Android Keystore niedostępny", error);
        }
    }

    private SecretKey getOrCreatePinKey() throws GeneralSecurityException, java.io.IOException {
        KeyStore keyStore = KeyStore.getInstance(KEYSTORE);
        keyStore.load(null);

        KeyStore.Entry existing = keyStore.getEntry(PIN_KEY_ALIAS, null);
        if (existing instanceof KeyStore.SecretKeyEntry) {
            return ((KeyStore.SecretKeyEntry) existing).getSecretKey();
        }

        KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_HMAC_SHA256,
                KEYSTORE
        );
        generator.init(new KeyGenParameterSpec.Builder(
                PIN_KEY_ALIAS,
                KeyProperties.PURPOSE_SIGN
        ).setDigests(KeyProperties.DIGEST_SHA256).build());
        return generator.generateKey();
    }

    private static String suffix(String uid) {
        return uid.length() <= 4 ? uid : uid.substring(uid.length() - 4);
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
