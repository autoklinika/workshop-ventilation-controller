package pl.autoklinika.workshopventilation.hmi;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.nfc.NfcAdapter;
import android.nfc.Tag;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.text.DateFormat;
import java.util.Date;
import java.util.Locale;

/** Native, offline service-access management screen available only after leaving Lock Task. */
public final class ServiceAccessActivity extends Activity implements NfcAdapter.ReaderCallback {

    private static final int BG = Color.rgb(9, 18, 28);
    private static final int PANEL = Color.rgb(18, 31, 45);
    private static final int TEXT = Color.WHITE;
    private static final int MUTED = Color.rgb(174, 190, 205);

    private ServiceAccessStore store;
    private NfcAdapter nfcAdapter;
    private LinearLayout cardsHost;
    private TextView nfcStatus;
    private TextView pinStatus;
    private boolean waitingForNewCard = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        store = new ServiceAccessStore(this);
        nfcAdapter = NfcAdapter.getDefaultAdapter(this);
        setContentView(buildUi());
        refreshCards();
        refreshPinStatus();
    }

    private View buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);
        root.setPadding(dp(28), dp(22), dp(28), dp(22));

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        TextView title = text("TRYB SERWISOWY", 26, TEXT);
        title.setTypeface(title.getTypeface(), android.graphics.Typeface.BOLD);
        TextView subtitle = text("Lokalne zarządzanie dostępem HMI · działa bez CM5 i sieci", 14, MUTED);
        titles.addView(title);
        titles.addView(subtitle);
        header.addView(titles, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

        Button back = button("WRÓĆ DO HMI");
        back.setOnClickListener(v -> finish());
        header.addView(back, new LinearLayout.LayoutParams(dp(190), dp(56)));
        root.addView(header);

        LinearLayout columns = new LinearLayout(this);
        columns.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams columnsParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f
        );
        columnsParams.topMargin = dp(20);
        root.addView(columns, columnsParams);

        LinearLayout cardsPanel = panel();
        TextView cardsTitle = text("KARTY NFC", 20, TEXT);
        cardsTitle.setTypeface(cardsTitle.getTypeface(), android.graphics.Typeface.BOLD);
        cardsPanel.addView(cardsTitle);
        nfcStatus = text("Karty serwisowe otwierają tryb serwisowy bez PIN-u.", 13, MUTED);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        statusParams.topMargin = dp(6);
        cardsPanel.addView(nfcStatus, statusParams);

        Button addCard = button("+ DODAJ KARTĘ");
        addCard.setOnClickListener(v -> beginAddCard());
        LinearLayout.LayoutParams addParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(54)
        );
        addParams.topMargin = dp(14);
        cardsPanel.addView(addCard, addParams);

        ScrollView cardsScroll = new ScrollView(this);
        cardsScroll.setFillViewport(true);
        cardsHost = new LinearLayout(this);
        cardsHost.setOrientation(LinearLayout.VERTICAL);
        cardsScroll.addView(cardsHost);
        LinearLayout.LayoutParams scrollParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f
        );
        scrollParams.topMargin = dp(12);
        cardsPanel.addView(cardsScroll, scrollParams);

        LinearLayout settingsPanel = panel();
        TextView pinTitle = text("PIN SERWISOWY", 20, TEXT);
        pinTitle.setTypeface(pinTitle.getTypeface(), android.graphics.Typeface.BOLD);
        settingsPanel.addView(pinTitle);
        pinStatus = text("", 13, MUTED);
        LinearLayout.LayoutParams pinStatusParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        pinStatusParams.topMargin = dp(6);
        settingsPanel.addView(pinStatus, pinStatusParams);

        Button changePin = button("ZMIEŃ PIN");
        changePin.setOnClickListener(v -> showChangePinDialog());
        LinearLayout.LayoutParams changeParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(54)
        );
        changeParams.topMargin = dp(14);
        settingsPanel.addView(changePin, changeParams);

        TextView systemTitle = text("SYSTEM ANDROID", 20, TEXT);
        systemTitle.setTypeface(systemTitle.getTypeface(), android.graphics.Typeface.BOLD);
        LinearLayout.LayoutParams systemTitleParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        systemTitleParams.topMargin = dp(34);
        settingsPanel.addView(systemTitle, systemTitleParams);

        TextView systemInfo = text(
                "Lock Task jest wyłączony do czasu powrotu do HMI. Możesz wejść do ustawień systemowych.",
                13,
                MUTED
        );
        LinearLayout.LayoutParams infoParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        infoParams.topMargin = dp(6);
        settingsPanel.addView(systemInfo, infoParams);

        Button androidSettings = button("OTWÓRZ USTAWIENIA ANDROIDA");
        androidSettings.setOnClickListener(v -> openAndroidSettings());
        LinearLayout.LayoutParams androidParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(54)
        );
        androidParams.topMargin = dp(14);
        settingsPanel.addView(androidSettings, androidParams);

        LinearLayout.LayoutParams left = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1.25f);
        LinearLayout.LayoutParams right = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 0.75f);
        right.leftMargin = dp(18);
        columns.addView(cardsPanel, left);
        columns.addView(settingsPanel, right);

        return root;
    }

    private LinearLayout panel() {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(20), dp(18), dp(20), dp(18));
        panel.setBackgroundColor(PANEL);
        return panel;
    }

    private TextView text(String value, int sp, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        return view;
    }

    private Button button(String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(14);
        button.setAllCaps(false);
        button.setMinHeight(dp(48));
        return button;
    }

    private void refreshCards() {
        cardsHost.removeAllViews();
        java.util.List<ServiceAccessStore.CardEntry> cards = store.getCards();
        if (cards.isEmpty()) {
            TextView empty = text("Brak zapisanych kart serwisowych.", 14, MUTED);
            empty.setPadding(0, dp(14), 0, dp(14));
            cardsHost.addView(empty);
            return;
        }

        DateFormat dateFormat = DateFormat.getDateTimeInstance(
                DateFormat.SHORT,
                DateFormat.SHORT,
                Locale.getDefault()
        );

        for (ServiceAccessStore.CardEntry card : cards) {
            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(0, dp(10), 0, dp(10));

            LinearLayout info = new LinearLayout(this);
            info.setOrientation(LinearLayout.VERTICAL);
            TextView label = text(card.label, 16, TEXT);
            label.setTypeface(label.getTypeface(), android.graphics.Typeface.BOLD);
            TextView uid = text("UID: " + card.uid, 12, MUTED);
            info.addView(label);
            info.addView(uid);
            if (card.lastUsedAtMs > 0L) {
                info.addView(text(
                        "Ostatnie użycie: " + dateFormat.format(new Date(card.lastUsedAtMs)),
                        11,
                        MUTED
                ));
            }
            row.addView(info, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));

            Button rename = button("NAZWA");
            rename.setOnClickListener(v -> showCardNameDialog(card.uid, card.label));
            row.addView(rename, new LinearLayout.LayoutParams(dp(110), dp(48)));

            Button remove = button("USUŃ");
            remove.setOnClickListener(v -> confirmRemove(card));
            LinearLayout.LayoutParams removeParams = new LinearLayout.LayoutParams(dp(100), dp(48));
            removeParams.leftMargin = dp(8);
            row.addView(remove, removeParams);

            cardsHost.addView(row);
            View divider = new View(this);
            divider.setBackgroundColor(Color.rgb(55, 72, 88));
            cardsHost.addView(divider, new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    dp(1)
            ));
        }
    }

    private void refreshPinStatus() {
        pinStatus.setText(store.isPinConfigured()
                ? "PIN jest skonfigurowany. Możesz zmienić go lokalnie bez przebudowy APK."
                : "PIN nie jest skonfigurowany. Ustaw go przed opuszczeniem trybu serwisowego.");
    }

    private void beginAddCard() {
        if (nfcAdapter == null || !nfcAdapter.isEnabled()) {
            Toast.makeText(this, "NFC jest wyłączone lub niedostępne", Toast.LENGTH_LONG).show();
            return;
        }
        waitingForNewCard = true;
        nfcStatus.setText("PRZYŁÓŻ NOWĄ KARTĘ NFC DO CZYTNIKA…");
        Toast.makeText(this, "Przyłóż kartę NFC", Toast.LENGTH_SHORT).show();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (nfcAdapter != null && nfcAdapter.isEnabled()) {
            int flags = NfcAdapter.FLAG_READER_NFC_A | NfcAdapter.FLAG_READER_SKIP_NDEF_CHECK;
            nfcAdapter.enableReaderMode(this, this, flags, null);
        }
    }

    @Override
    protected void onPause() {
        if (nfcAdapter != null) {
            nfcAdapter.disableReaderMode(this);
        }
        super.onPause();
    }

    @Override
    public void onTagDiscovered(Tag tag) {
        if (!waitingForNewCard) {
            return;
        }
        String uid = toHexCompact(tag.getId());
        if (uid.isEmpty()) {
            return;
        }
        waitingForNewCard = false;
        runOnUiThread(() -> {
            nfcStatus.setText("Odczytano UID: " + uid);
            ServiceAccessStore.CardEntry existing = null;
            for (ServiceAccessStore.CardEntry card : store.getCards()) {
                if (card.uid.equals(uid)) {
                    existing = card;
                    break;
                }
            }
            showCardNameDialog(uid, existing == null ? "Karta " + suffix(uid) : existing.label);
        });
    }

    private void showCardNameDialog(String uid, String currentLabel) {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setText(currentLabel);
        input.setSelectAllOnFocus(true);
        input.setHint("Nazwa karty");

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Karta NFC")
                .setMessage("UID: " + uid)
                .setView(input)
                .setNegativeButton("Anuluj", null)
                .setPositiveButton("Zapisz", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(v -> {
                    String label = input.getText().toString().trim();
                    if (label.isEmpty()) {
                        input.setError("Podaj nazwę karty");
                        return;
                    }
                    store.addOrRenameCard(uid, label);
                    dialog.dismiss();
                    nfcStatus.setText("Karta zapisana: " + label);
                    refreshCards();
                }));
        dialog.show();
    }

    private void confirmRemove(ServiceAccessStore.CardEntry card) {
        new AlertDialog.Builder(this)
                .setTitle("Usuń kartę")
                .setMessage(card.label + "\nUID: " + card.uid)
                .setNegativeButton("Anuluj", null)
                .setPositiveButton("Usuń", (dialog, which) -> {
                    if (!store.isPinConfigured() && store.getCards().size() <= 1) {
                        Toast.makeText(
                                this,
                                "Najpierw ustaw PIN — nie można usunąć ostatniej metody dostępu",
                                Toast.LENGTH_LONG
                        ).show();
                        return;
                    }
                    store.removeCard(card.uid);
                    refreshCards();
                })
                .show();
    }

    private void showChangePinDialog() {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(24), 0, dp(24), 0);

        EditText first = pinInput("Nowy PIN");
        EditText second = pinInput("Powtórz nowy PIN");
        form.addView(first);
        LinearLayout.LayoutParams secondParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        secondParams.topMargin = dp(10);
        form.addView(second, secondParams);

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Zmień PIN serwisowy")
                .setMessage("Tryb serwisowy jest już uwierzytelniony. Ustaw nowy PIN.")
                .setView(form)
                .setNegativeButton("Anuluj", null)
                .setPositiveButton("Zapisz", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setOnClickListener(v -> {
                    String a = first.getText().toString();
                    String b = second.getText().toString();
                    if (a.length() < 4) {
                        first.setError("PIN musi mieć co najmniej 4 cyfry");
                        return;
                    }
                    if (!a.matches("[0-9]+")) {
                        first.setError("PIN może zawierać tylko cyfry");
                        return;
                    }
                    if (!a.equals(b)) {
                        second.setError("PIN-y nie są zgodne");
                        return;
                    }
                    try {
                        store.setPin(a);
                    } catch (RuntimeException error) {
                        Toast.makeText(this, "Nie udało się zapisać PIN-u", Toast.LENGTH_LONG).show();
                        return;
                    }
                    dialog.dismiss();
                    refreshPinStatus();
                    Toast.makeText(this, "PIN serwisowy zmieniony", Toast.LENGTH_SHORT).show();
                }));
        dialog.show();
        first.requestFocus();
        if (dialog.getWindow() != null) {
            dialog.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE);
        }
    }

    private EditText pinInput(String hint) {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setHint(hint);
        input.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        return input;
    }

    private void openAndroidSettings() {
        try {
            startActivity(new Intent(Settings.ACTION_SETTINGS));
        } catch (RuntimeException error) {
            Toast.makeText(this, "Nie udało się otworzyć ustawień Androida", Toast.LENGTH_LONG).show();
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static String toHexCompact(byte[] data) {
        if (data == null) {
            return "";
        }
        StringBuilder out = new StringBuilder();
        for (byte value : data) {
            out.append(String.format(Locale.US, "%02X", value & 0xFF));
        }
        return out.toString();
    }

    private static String suffix(String uid) {
        return uid.length() <= 4 ? uid : uid.substring(uid.length() - 4);
    }
}
