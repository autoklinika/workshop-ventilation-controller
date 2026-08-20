# Workshop Ventilation HMI — iiyama Android

## Status

**Stage 4 — FINAL HARDWARE VALIDATION PASS (2026-08-20).**

Finalny raport walidacji: `docs/reports/IYAMA_ANDROID_KIOSK_STAGE4_FINAL_VALIDATION_2026-08-20_PL.md`.

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

```powershell
cd C:\PROJEKTY\wvc-iiyama-kiosk

git switch agent/iiyama-android-kiosk-stage4-service-access
git pull --ff-only origin agent/iiyama-android-kiosk-stage4-service-access

cd hmi\iiyama-android

.\tools\configure-admin-settings-pin.ps1
.\tools\build-debug.ps1
.\tools\deploy-debug.ps1
```

`deploy-debug.ps1` uses `adb install -r -t`; app-private service cards and the normal service PIN are preserved across this update path.

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
