# Workshop Ventilation HMI — iiyama Android

Branch: `agent/iiyama-android-kiosk-stage2`

## Stage 2 scope — native Android kiosk

This module is the native Android shell for the iiyama ProLite TW1025LASC-B3PNR HMI.

Stage 2 keeps the Stage 1 WebView/NFC functionality and adds a native Android dedicated-device kiosk path independent of the iiyama Kiosk Mode implementation:

- `DeviceAdminReceiver` suitable for provisioning the package as Android Device Owner,
- Device Owner allowlisting of the HMI package for Lock Task Mode,
- `LOCK_TASK_FEATURE_NONE`,
- automatic entry into Lock Task Mode when Device Owner is active,
- `BOOT_COMPLETED` receiver that starts the HMI after boot only when the package is Device Owner,
- `android:lockTaskMode="if_whitelisted"` on `MainActivity`,
- Stage 2 build marked `android:testOnly="true"` so the Device Owner can be removed during hardware validation,
- deploy script installs the test build with `adb install -r -t`.

The iiyama Kiosk Mode, iiyama Auto Launch and iiyama Exit Password are not part of the Stage 2 kiosk architecture.

## Safety / development status

Stage 2 is intentionally a validation build. Do not merge it into `main` and do not convert it into a non-test Device Owner build until the dedicated-device behavior has been validated on the physical HMI.

The Stage 2 build intentionally does not yet provide a local service-PIN exit UI. During validation, ADB remains the recovery path. A production service exit will be added only after Lock Task and boot behavior are validated.

## Provisioning preconditions

Before `dpm set-device-owner`:

- only Android user `0` should exist,
- there must be no Android accounts,
- there must be no existing Device Owner or Profile Owner,
- the Stage 2 APK must already be installed.

Expected checks on the current iiyama Android 13 build:

```powershell
adb shell dpm list-owners
adb shell pm list users
adb shell dumpsys account
```

## Provision as Device Owner

Component:

```text
pl.autoklinika.workshopventilation.hmi/.KioskDeviceAdminReceiver
```

Provisioning command:

```powershell
adb shell dpm set-device-owner --device-owner-only pl.autoklinika.workshopventilation.hmi/.KioskDeviceAdminReceiver
```

Validation:

```powershell
adb shell dpm list-owners
adb shell dumpsys activity activities | grep -A8 -B2 LockTaskController
```

For this Stage 2 `testOnly` build, rollback is available with:

```powershell
adb shell dpm remove-active-admin pl.autoklinika.workshopventilation.hmi/.KioskDeviceAdminReceiver
```

Do not use the rollback command after the project is converted to a production/non-test Device Owner build.

## Existing HMI functionality

- fullscreen / immersive Android activity,
- WebView loading Workshop Ventilation WebGUI V2,
- WebView navigation restricted to `http://192.168.1.64:18091/`,
- NFC ReaderMode for NFC-A cards,
- NFC UID forwarding into the loaded WebGUI as the `wvc:nfc-scan` JavaScript event,
- duplicate-scan debounce,
- automatic retry when the main WebGUI frame cannot be loaded,
- screen kept awake while the HMI is active,
- BACK button suppressed.

## NFC event contract

The Android shell dispatches:

```javascript
window.addEventListener('wvc:nfc-scan', (event) => {
    console.log(event.detail);
});
```

Payload example:

```json
{
  "uid": "A42F4CE1",
  "uid_display": "A4 2F 4C E1",
  "source": "nfc",
  "timestamp_ms": 1787060000000
}
```

The Android shell does **not** decide whether a card is valid. The target architecture is that the UID is verified by the CM5 and the CM5 remains the source of truth for users, cards, roles and permissions.

## Build environment used in the workshop

- Windows + VS Code
- Android SDK: `%LOCALAPPDATA%\Android\Sdk`
- Android platform: `android-37.0`
- Android Build Tools: `36.0.0`
- Android Gradle Plugin: `9.2.1`
- Gradle: `9.4.1`
- JDK: Android Studio JBR

`local.properties` is intentionally not committed. `tools\build-debug.ps1` creates it automatically when missing.

## Sync branch in VS Code

```powershell
git fetch origin
git switch --track origin/agent/iiyama-android-kiosk-stage2
```

If the local branch already exists:

```powershell
git fetch origin
git switch agent/iiyama-android-kiosk-stage2
git pull --ff-only origin agent/iiyama-android-kiosk-stage2
```

Then:

```powershell
cd hmi\iiyama-android
```

## Build

```powershell
.\tools\build-debug.ps1
```

Expected APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

## Install and launch on iiyama

```powershell
.\tools\deploy-debug.ps1
```

The Stage 2 deploy script uses `adb install -r -t` because the validation APK is deliberately marked `testOnly`.

## Stage 2 hardware validation

1. Install the Stage 2 APK.
2. Provision `KioskDeviceAdminReceiver` as Device Owner.
3. Launch the HMI and verify `mLockTaskModeState=LOCKED`.
4. Verify HOME/BACK/RECENTS cannot leave the HMI.
5. Verify WebGUI V2 still loads from port `18091`.
6. Verify NFC scan forwarding still works.
7. Disable the iiyama Boot App / Kiosk Mode so only the native Android path remains.
8. Reboot and verify `BootReceiver` starts the HMI and Lock Task Mode returns automatically.
9. Verify ADB Wi-Fi remains available as the Stage 2 recovery path.

Do not merge this branch into `main` without explicit project-owner approval.
