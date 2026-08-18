# Workshop Ventilation HMI — iiyama Android

Branch: `agent/iiyama-hmi-stage1`

## Stage 1 scope

This module is the native Android shell for the iiyama ProLite TW1025LASC-B3PNR HMI.

Current scope:

- fullscreen / immersive Android activity,
- WebView loading Workshop Ventilation WebGUI V2,
- WebView navigation restricted to `http://192.168.1.64:18091/`,
- NFC ReaderMode for NFC-A cards,
- NFC UID forwarding into the loaded WebGUI as the `wvc:nfc-scan` JavaScript event,
- duplicate-scan debounce,
- automatic retry when the main WebGUI frame cannot be loaded,
- screen kept awake while the HMI is active,
- BACK button suppressed.

Not implemented in Stage 1:

- CM5-side NFC card database,
- CM5-side authentication / authorization,
- RGB LED bridge,
- RFID 125 kHz bridge,
- iiyama production kiosk configuration,
- Android autostart / device-owner policy.

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

`local.properties` is intentionally not committed.

Create it locally once:

```powershell
$sdk = "$env:LOCALAPPDATA\Android\Sdk" -replace '\\','/'
"sdk.dir=$sdk" | Set-Content .\local.properties -Encoding ASCII
```

## Sync branch in VS Code

From the local repository:

```powershell
git fetch origin
git switch agent/iiyama-hmi-stage1
git pull --ff-only origin agent/iiyama-hmi-stage1
cd hmi\iiyama-android
```

If the branch does not exist locally yet:

```powershell
git fetch origin
git switch --track origin/agent/iiyama-hmi-stage1
cd hmi\iiyama-android
```

## Build

The project intentionally does not commit a Gradle wrapper JAR at this stage. Use the already installed workshop Gradle distribution:

```powershell
C:\Android\gradle\gradle-9.4.1\bin\gradle.bat assembleDebug
```

Expected APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

## Install on iiyama

```powershell
C:\Android\platform-tools\adb.exe install -r .\app\build\outputs\apk\debug\app-debug.apk
```

Launch:

```powershell
C:\Android\platform-tools\adb.exe shell am start -n pl.autoklinika.workshopventilation.hmi/.MainActivity
```

## Stage 1 validation

1. The WebGUI V2 must fill the display without Chrome UI.
2. Android system bars should be hidden in immersive mode.
3. The display must stay awake.
4. BACK must not exit the HMI.
5. With CM5 reachable, WebGUI V2 must load from port `18091`.
6. Present an NFC-A / MIFARE Classic card.
7. A toast such as `NFC: A42F4CE1` must appear.
8. A second card must produce a different UID.
9. Loss of the WebGUI main frame should trigger a retry after 3 seconds.

Do not merge this branch into `main` without explicit project-owner approval.
