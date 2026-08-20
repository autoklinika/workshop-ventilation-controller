$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Adb = 'C:\Android\platform-tools\adb.exe'
$Apk = Join-Path $ProjectRoot 'app\build\outputs\apk\debug\app-debug.apk'
$Component = 'pl.autoklinika.workshopventilation.hmi/.MainActivity'

function Get-ReadyAdbDevices {
    $lines = & $Adb devices
    if ($LASTEXITCODE -ne 0) {
        throw "ADB devices failed with exit code $LASTEXITCODE"
    }

    @(
        $lines |
            Select-Object -Skip 1 |
            Where-Object { $_ -match "^\S+\s+device$" } |
            ForEach-Object { ($_ -split "\s+")[0] }
    )
}

function Try-ReconnectWirelessAdb {
    Write-Host '[ADB] No ready device. Trying wireless reconnect...'

    & $Adb reconnect | Out-Host
    Start-Sleep -Milliseconds 800

    $ready = @(Get-ReadyAdbDevices)
    if ($ready.Count -gt 0) {
        return $ready
    }

    $mdns = @(& $Adb mdns services 2>$null)
    $endpoints = @(
        $mdns |
            Where-Object { $_ -match '_adb-tls-connect\._tcp' } |
            ForEach-Object {
                if ($_ -match '(\d{1,3}(?:\.\d{1,3}){3}:\d+)') {
                    $Matches[1]
                }
            } |
            Select-Object -Unique
    )

    if ($endpoints.Count -eq 1) {
        Write-Host "[ADB] Found paired wireless endpoint: $($endpoints[0])"
        & $Adb connect $endpoints[0] | Out-Host
        Start-Sleep -Milliseconds 800
        return @(Get-ReadyAdbDevices)
    }

    if ($endpoints.Count -gt 1) {
        Write-Host '[ADB] More than one paired wireless endpoint was discovered:'
        $endpoints | ForEach-Object { Write-Host "      $_" }
    }

    return @()
}

if (-not (Test-Path $Adb)) {
    throw "ADB not found: $Adb"
}

if (-not (Test-Path $Apk)) {
    throw "APK not found: $Apk. Run tools\build-debug.ps1 first."
}

Write-Host '===== WORKSHOP VENTILATION HMI DEPLOY ====='
Write-Host "APK: $Apk"
Write-Host

Write-Host '[1/4] Starting/checking ADB server...'
& $Adb start-server | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "ADB server failed with exit code $LASTEXITCODE"
}

Write-Host '[2/4] Looking for the iiyama ADB device...'
$devices = @(Get-ReadyAdbDevices)
if ($devices.Count -eq 0) {
    $devices = @(Try-ReconnectWirelessAdb)
}

if ($devices.Count -eq 0) {
    Write-Host
    Write-Host 'No ready ADB device was found.' -ForegroundColor Yellow
    Write-Host 'On the iiyama open: Developer options -> Wireless debugging.'
    Write-Host 'Reconnect/pair the panel there, then run this same script again:'
    Write-Host '  .\tools\deploy-debug.ps1'
    throw 'No ADB device is ready.'
}

if ($devices.Count -gt 1) {
    Write-Host
    Write-Host 'More than one ready ADB device is connected:' -ForegroundColor Yellow
    $devices | ForEach-Object { Write-Host "  $_" }
    throw 'Disconnect extra ADB devices before deploying the HMI.'
}

$Serial = $devices[0]
Write-Host "[ADB] Using device: $Serial"

Write-Host '[3/4] Installing debug/test APK...'
& $Adb -s $Serial install -r -t $Apk | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "ADB install failed with exit code $LASTEXITCODE"
}

Write-Host '[4/4] Launching Workshop Ventilation HMI...'
& $Adb -s $Serial shell am force-stop 'pl.autoklinika.workshopventilation.hmi' | Out-Null
& $Adb -s $Serial shell am start -W -n $Component | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "HMI launch failed with exit code $LASTEXITCODE"
}

Write-Host
Write-Host 'Workshop Ventilation HMI installed and launched.' -ForegroundColor Green
