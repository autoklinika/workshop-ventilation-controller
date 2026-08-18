$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Adb = 'C:\Android\platform-tools\adb.exe'
$Apk = Join-Path $ProjectRoot 'app\build\outputs\apk\debug\app-debug.apk'
$Component = 'pl.autoklinika.workshopventilation.hmi/.MainActivity'

if (-not (Test-Path $Adb)) {
    throw "ADB not found: $Adb"
}

if (-not (Test-Path $Apk)) {
    throw "APK not found: $Apk. Run tools\build-debug.ps1 first."
}

& $Adb get-state | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'No ADB device is ready.'
}

& $Adb install -r $Apk
if ($LASTEXITCODE -ne 0) {
    throw "ADB install failed with exit code $LASTEXITCODE"
}

& $Adb shell am start -n $Component
if ($LASTEXITCODE -ne 0) {
    throw "HMI launch failed with exit code $LASTEXITCODE"
}

Write-Host 'Workshop Ventilation HMI installed and launched.'
