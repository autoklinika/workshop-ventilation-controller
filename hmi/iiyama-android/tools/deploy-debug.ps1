param(
    [string]$Device = '192.168.1.23:5555'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Adb = 'C:\Android\platform-tools\adb.exe'
$Apk = Join-Path $ProjectRoot 'app\build\outputs\apk\debug\app-debug.apk'
$Gradle = Join-Path $ProjectRoot 'app\build.gradle'
$Package = 'pl.autoklinika.workshopventilation.hmi'
$Component = "$Package/.MainActivity"

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

function Try-ConnectPreferredDevice {
    Write-Host "[ADB] Trying preferred HMI endpoint: $Device"
    & $Adb connect $Device | Out-Host
    Start-Sleep -Milliseconds 800
    @(Get-ReadyAdbDevices)
}

function Try-ReconnectWirelessAdb {
    Write-Host '[ADB] Preferred endpoint is not ready. Trying wireless reconnect...'

    & $Adb reconnect | Out-Host
    Start-Sleep -Milliseconds 800

    $ready = @(Get-ReadyAdbDevices)
    if ($ready -contains $Device) {
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

    return $ready
}

function Select-HmiDevice {
    param([string[]]$ReadyDevices)

    # The iiyama can appear twice in `adb devices`: once as the stable TCP endpoint
    # and once as the Android Wireless Debugging mDNS/TLS transport. Those are two
    # transports to the same physical panel, not two different devices. Prefer the
    # known stable endpoint whenever it is present.
    if ($ReadyDevices -contains $Device) {
        $others = @($ReadyDevices | Where-Object { $_ -ne $Device })
        if ($others.Count -gt 0) {
            Write-Host '[ADB] Additional ready ADB transport(s) detected and ignored:' -ForegroundColor DarkYellow
            $others | ForEach-Object { Write-Host "      $_" }
        }
        return $Device
    }

    if ($ReadyDevices.Count -eq 1) {
        Write-Host "[ADB] Preferred endpoint $Device is unavailable; using the only ready device."
        return $ReadyDevices[0]
    }

    if ($ReadyDevices.Count -gt 1) {
        Write-Host
        Write-Host "Preferred HMI endpoint '$Device' is not present and more than one ready ADB device exists:" -ForegroundColor Yellow
        $ReadyDevices | ForEach-Object { Write-Host "  $_" }
        throw 'Cannot safely choose the HMI target. Pass -Device <serial-or-endpoint> explicitly.'
    }

    return $null
}

function Get-ExpectedBuildVersion {
    if (-not (Test-Path $Gradle)) {
        throw "Gradle file not found: $Gradle"
    }

    $text = Get-Content -Raw $Gradle
    $nameMatch = [regex]::Match($text, "versionName\s*=\s*'([^']+)'")
    $codeMatch = [regex]::Match($text, 'versionCode\s*=\s*(\d+)')
    if (-not $nameMatch.Success -or -not $codeMatch.Success) {
        throw 'Unable to read versionName/versionCode from app\build.gradle'
    }

    [pscustomobject]@{
        Name = $nameMatch.Groups[1].Value
        Code = [int]$codeMatch.Groups[1].Value
    }
}

function Get-InstalledBuildVersion {
    param([string]$Serial)

    $dump = (& $Adb -s $Serial shell dumpsys package $Package 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read installed package metadata for $Package"
    }

    $nameMatch = [regex]::Match($dump, 'versionName=([^\r\n\s]+)')
    $codeMatch = [regex]::Match($dump, 'versionCode=(\d+)')
    if (-not $nameMatch.Success -or -not $codeMatch.Success) {
        throw "Unable to parse installed version for $Package"
    }

    [pscustomobject]@{
        Name = $nameMatch.Groups[1].Value.Trim()
        Code = [int]$codeMatch.Groups[1].Value
    }
}

if (-not (Test-Path $Adb)) {
    throw "ADB not found: $Adb"
}

if (-not (Test-Path $Apk)) {
    throw "APK not found: $Apk. Run tools\build-debug.ps1 first."
}

$expected = Get-ExpectedBuildVersion

Write-Host '===== WORKSHOP VENTILATION HMI DEPLOY ====='
Write-Host "APK:       $Apk"
Write-Host "Target:    $Device"
Write-Host "Expected:  versionCode $($expected.Code), versionName $($expected.Name)"
Write-Host

Write-Host '[1/5] Starting/checking ADB server...'
& $Adb start-server | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "ADB server failed with exit code $LASTEXITCODE"
}

Write-Host '[2/5] Looking for the iiyama ADB device...'
$devices = @(Get-ReadyAdbDevices)

if (-not ($devices -contains $Device)) {
    $devices = @(Try-ConnectPreferredDevice)
}

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

$Serial = Select-HmiDevice -ReadyDevices $devices
if (-not $Serial) {
    throw 'No safe HMI ADB target could be selected.'
}
Write-Host "[ADB] Using device: $Serial"

Write-Host '[3/5] Installing debug/test APK...'
& $Adb -s $Serial install -r -t $Apk | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "ADB install failed with exit code $LASTEXITCODE"
}

Write-Host '[4/5] Verifying installed APK version...'
$installed = Get-InstalledBuildVersion -Serial $Serial
Write-Host "Installed: versionCode $($installed.Code), versionName $($installed.Name)"
if ($installed.Code -ne $expected.Code -or $installed.Name -ne $expected.Name) {
    throw "STALE APK DETECTED. Source expects $($expected.Code)/$($expected.Name), but panel has $($installed.Code)/$($installed.Name). Re-run .\tools\build-debug.ps1 and deploy again."
}
Write-Host '[APK] Version verification: PASS' -ForegroundColor Green

Write-Host '[5/5] Launching Workshop Ventilation HMI...'
& $Adb -s $Serial shell am force-stop $Package | Out-Null
& $Adb -s $Serial shell am start -W -n $Component | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "HMI launch failed with exit code $LASTEXITCODE"
}

Write-Host
Write-Host 'Workshop Ventilation HMI installed, verified and launched.' -ForegroundColor Green
