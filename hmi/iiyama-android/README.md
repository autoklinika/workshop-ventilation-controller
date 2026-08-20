# Workshop Ventilation HMI — iiyama Android

Current development branch: `agent/iiyama-android-kiosk-stage4-service-access`

## Stage 4 — local service access management

Stage 4 builds on the validated native Android dedicated-device kiosk:

- HMI package remains Android Device Owner,
- HMI starts automatically after `BOOT_COMPLETED`,
- Android Lock Task returns automatically after boot,
- iiyama vendor kiosk is not used,
- service exit works by an allowed NFC card or by 5 taps on the active `PULPIT` tile followed by the service PIN,
- after authentication a native offline `ServiceAccessActivity` opens with Lock Task disabled,
- service cards can be added by touching them to the panel, renamed and removed locally,
- the service PIN can be changed locally,
- Android Settings can be opened from the service screen,
- returning to HMI re-arms Lock Task automatically.

The service screen, PIN validation and NFC service-card allowlist do not depend on CM5, WebGUI or network connectivity.

## Service credential storage

Stage 4 stores service configuration in app-private Android storage.

- NFC UIDs and labels: private `SharedPreferences` JSON.
- Service PIN: never stored in plaintext. A HMAC-SHA256 verification value is generated with a key held by Android Keystore.
- Existing Stage 3 build-time card UIDs are imported once on first Stage 4 start.
- Existing Stage 3 PIN remains available only as a migration fallback; after the first successful PIN verification it is re-saved using the Stage 4 Keystore path.
- Updating the APK does not require re-entering locally managed cards/PIN.

`service-access.properties` remains ignored by git and is retained only so a Stage 3-configured hardware unit can migrate without losing access.

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

Expected kiosk state:

```text
mLockTaskModeState=LOCKED
mLockTaskPackages (userId:packages)=
  u0:[pl.autoklinika.workshopventilation.hmi]
```

## Service exit methods

### NFC

An NFC UID stored in the local service-card list leaves Lock Task immediately and opens the local service screen.

### PIN

While the `PULPIT` view is active, tap the `PULPIT` navigation tile 5 times within 4 seconds. The native PIN dialog appears. A valid PIN leaves Lock Task and opens the local service screen.

After 5 invalid PIN attempts the PIN entry is blocked for 30 seconds.

## Local service screen

Available actions:

- `+ DODAJ KARTĘ` → touch the new card → enter a label → save,
- rename a card,
- remove a card,
- view UID and last-use timestamp,
- change service PIN,
- open Android Settings,
- `WRÓĆ DO HMI` → return to HMI and automatically re-arm kiosk mode.

A last card cannot be removed when no service PIN is configured.

## Device Owner

Component:

```text
pl.autoklinika.workshopventilation.hmi/.KioskDeviceAdminReceiver
```

Device Owner is provisioned only once. Do not run `dpm set-device-owner` again when updating Stage 3 → Stage 4.

Validation:

```powershell
adb shell dpm list-owners
adb shell "dumpsys activity activities | grep -A8 -B2 'LockTaskController'"
```

The validation APK is still marked `android:testOnly="true"` so recovery remains possible during hardware validation.

## Build / deploy

```powershell
cd C:\PROJEKTY\wvc-iiyama-kiosk

git fetch origin
git switch -c agent/iiyama-android-kiosk-stage4-service-access `
  --track origin/agent/iiyama-android-kiosk-stage4-service-access

cd hmi\iiyama-android
.\tools\build-debug.ps1
.\tools\deploy-debug.ps1
```

If the local Stage 4 branch already exists:

```powershell
git switch agent/iiyama-android-kiosk-stage4-service-access
git pull --ff-only origin agent/iiyama-android-kiosk-stage4-service-access
```

`deploy-debug.ps1` uses `adb install -r -t`; app-private Stage 4 service settings are preserved across this update path.

## Stage 4 hardware validation

1. Update the Stage 3 hardware with the Stage 4 APK without reprovisioning Device Owner.
2. Verify the existing service card still exits the kiosk.
3. Verify the existing service PIN still exits the kiosk.
4. Verify the local service screen opens and Lock Task is `NONE` while it is active.
5. Add a second NFC card using only the HMI UI.
6. Return to HMI and verify the new card opens service mode.
7. Rename the card and verify the label persists after reboot.
8. Change the service PIN locally and verify the old PIN no longer works while the new PIN does.
9. Remove a test card and verify it no longer opens service mode.
10. Open Android Settings from the service screen and return to the service screen.
11. Choose `WRÓĆ DO HMI` and verify Lock Task returns to `LOCKED`.
12. Reboot the panel and verify HMI autostart + `LOCKED` still work and Stage 4 card/PIN changes persist.

Do not merge this branch into `main` without explicit project-owner approval.
