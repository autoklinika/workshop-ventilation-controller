# Workshop Ventilation HMI — iiyama Android

## Status

**Stage 4 — FINAL HARDWARE VALIDATION PASS (2026-08-20).**

Finalny raport walidacji: `docs/reports/IYAMA_ANDROID_KIOSK_STAGE4_FINAL_VALIDATION_2026-08-20_PL.md`.

**RGB Alert LED Stage 1 — finalna paleta zakodowana; pełna walidacja alert-flow na sprzęcie oczekuje.**

Raport implementacji: `docs/reports/IYAMA_ANDROID_LED_ALERT_STAGE1_IMPLEMENTATION_PL.md`.

## Stage 4 — local service access management

Stage 4 builds on the validated native Android dedicated-device kiosk:

- HMI package remains Android Device Owner,
- HMI starts automatically after `BOOT_COMPLETED`,
- Android Lock Task returns automatically after boot,
- iiyama vendor kiosk is not used,
- service entry works by an allowed NFC card or by 5 taps on the active `PULPIT` tile followed by the normal service PIN,
- successful NFC/PIN authentication opens a native two-tile service menu while kiosk Lock Task remains active,
- `ANDROID` deliberately leaves Lock Task and opens the Android launcher,
- `USTAWIENIA` keeps the kiosk locked and requires a second, fixed administrator PIN,
- only after that fixed administrator PIN is accepted can service NFC cards and the normal service PIN be edited,
- returning to HMI keeps or restores Lock Task automatically.

The service menu, PIN validation and NFC service-card allowlist do not depend on CM5, WebGUI or network connectivity.

## Credential model

There are two different PIN roles.

### Normal service PIN

The normal service PIN is one of the two ways to enter the service menu. It can be changed locally from the protected service-settings editor.

Stage 4 stores the normal service PIN in app-private Android storage. The PIN is never stored in plaintext; its verifier is protected with Android Keystore. NFC UIDs and labels are kept in private app storage.

### Fixed administrator PIN

The `USTAWIENIA` tile requires a separate administrator PIN. This PIN:

- must be different from the normal service PIN,
- has no change option anywhere in the HMI,
- is compiled into a given APK only as a salted SHA-256 verifier,
- is supplied locally from ignored `service-access.properties`, so the credential itself is not committed to Git.

Configure it before a local hardware build with:

```powershell
.\tools\configure-admin-settings-pin.ps1
```

The script asks for the administrator PIN twice using masked input and updates only its local verifier while preserving existing service migration values.

`service-access.properties` remains ignored by git.

## Normal kiosk behavior

The native Android shell:

- loads WebGUI V2 from `http://192.168.1.64:18091/`,
- keeps the screen awake,
- hides system bars,
- blocks BACK,
- allowlists itself for Lock Task as Device Owner,
- enters Lock Task automatically,
- retries kiosk enforcement during the iiyama Android boot transition,
- starts after boot via `BootReceiver`.

Expected normal state:

```text
mLockTaskModeState=LOCKED
mLockTaskPackages (userId:packages)=
  u0:[pl.autoklinika.workshopventilation.hmi]
```

## Service entry methods

### NFC

A service NFC UID opens the two-tile service menu. Lock Task stays `LOCKED` at this point.

### PIN

While the `PULPIT` view is active, tap the `PULPIT` navigation tile 5 times within 4 seconds. Enter the normal service PIN. A valid PIN opens the same two-tile service menu and Lock Task stays `LOCKED`.

After 5 invalid normal service PIN attempts the entry is blocked for 30 seconds.

## Two-tile service menu

### ANDROID

`ANDROID` is the only service-menu action that deliberately leaves the kiosk.

Expected transition:

```text
LOCKED + HMI allowlisted
    -> ANDROID
NONE + empty Lock Task allowlist
    -> Android launcher
```

The HMI task is removed after opening Android. When the HMI application is launched again, Device Owner policy and Lock Task are restored.

### USTAWIENIA

`USTAWIENIA` does not leave Lock Task. It first displays a native fixed-administrator-PIN dialog.

After successful administrator authentication the local editor allows:

- `+ DODAJ KARTĘ` → touch the new card → enter a label → save,
- rename a card,
- remove a card,
- view UID and last-use timestamp,
- change the normal service PIN.

The fixed administrator PIN itself cannot be changed from this editor.

A last service card cannot be removed when no normal service PIN is configured.

## Device Owner

Component:

```text
pl.autoklinika.workshopventilation.hmi/.KioskDeviceAdminReceiver
```

Device Owner is provisioned only once. Do not run `dpm set-device-owner` again when updating the APK.

Validation:

```powershell
adb shell dpm list-owners
adb shell "dumpsys activity activities | grep -A8 -B2 'LockTaskController'"
```

The current APK is still marked `android:testOnly="true"`; this is retained as a deliberate recovery path while the Android shell remains under active development.

## Build / deploy

For the current RGB LED Stage 1 branch:

```powershell
cd C:\PROJEKTY\wvc-iiyama-kiosk

git switch agent/iiyama-led-alert-stage1
git pull --ff-only origin agent/iiyama-led-alert-stage1

cd hmi\iiyama-android

.\tools\build-debug.ps1
.\tools\deploy-debug.ps1
```

`deploy-debug.ps1` uses `adb install -r -t`; app-private service cards and the normal service PIN are preserved across this update path.

Current LED build:

```text
versionCode 10
versionName 0.5.3-led-alert-palette
```

## Stage 4 hardware validation — PASS

Na docelowym panelu iiyama TW1025LASC-B3PNR potwierdzono:

- Device Owner pozostaje aktywny po aktualizacji APK,
- normalna praca HMI ma `mLockTaskModeState=LOCKED`,
- NFC otwiera dwukafelkowe menu serwisowe bez opuszczania kiosku,
- `5× PULPIT + normalny PIN serwisowy` otwiera to samo menu,
- lokalne dodawanie kart NFC i zmiana normalnego PIN-u działają,
- `USTAWIENIA` wymagają drugiego, stałego PIN-u administratora,
- poprawny stały PIN otwiera edycję kart i normalnego PIN-u,
- stałego PIN-u administratora nie można zmienić z HMI,
- `ANDROID` przełącza Lock Task na `NONE`, czyści allowlistę i otwiera system Android,
- po ponownym uruchomieniu HMI Lock Task wraca do `LOCKED` i pakiet HMI wraca na allowlistę.

Szczegółowy zapis testów i wyniki znajdują się w finalnym raporcie Stage 4.

## RGB Alert LED Stage 1

RGB jest sterowane natywnie przez Androida, niezależnie od WebView. Aplikacja odpytuje istniejące `/api/v1/alerts` co 2 s; `ventilation-core` pozostaje źródłem prawdy i nie został zmodyfikowany dla tej funkcji.

Priorytet lokalnej wizualizacji:

```text
CRITICAL > ALARM > WARNING > INFO > SERVICE > NORMAL
```

Finalne mapowanie:

- NORMAL → zielony stały,
- SERVICE / Android → niebieski stały, o ile nie ma aktywnego alertu,
- INFO → niebieski; UNACK miga, ACK stały,
- WARNING → żółty; UNACK miga, ACK stały,
- ALARM → pomarańczowy; UNACK miga, ACK stały,
- CRITICAL → czerwony; UNACK szybko miga, ACK stały,
- przed pierwszym poprawnym snapshotem → biały wolno migający,
- utrata komunikacji po wcześniejszym połączeniu przez ponad 6 s → czerwony szybko migający.

ACK nie obniża priorytetu i nie zmienia koloru.

Sprzętowo potwierdzona paleta docelowego B3:

```text
0x02 = OFF
0x03 = LED ON
0x04 = RED / CRITICAL
0x05 = GREEN / NORMAL
0x06 = BLUE / INFO + SERVICE
0x07 = WHITE / STARTUP UNKNOWN
0x08 = ORANGE / ALARM
0x10 = YELLOW / WARNING
```

Potwierdzone efekty `0x0B`, `0x0F`, `0x13`, `0x17` nie są używane przez AlertV2, ponieważ mają własne zachowanie kolorystyczne. Próby uzyskania fade bieżącego koloru przez efekt producenta, custom RGB i brightness nie dały poprawnego fade na B3. Starszy interfejs `/dev/ledjni` z demo B1 nie istnieje na docelowym B3.

Sterownik używa zatem statycznego koloru oraz kontrolowanego programowo ON/OFF dla stanów UNACK. Po OFF wysyła `0x03`, a następnie właściwy statyczny kolor; przy zwykłej zmianie koloru bez OFF nie powtarza `0x03`.

Test palety:

```powershell
.\tools\test-led-palette.ps1
```

Skrypt sprawdza kolejno zielony, niebieski, żółty, pomarańczowy, czerwony i biały.
