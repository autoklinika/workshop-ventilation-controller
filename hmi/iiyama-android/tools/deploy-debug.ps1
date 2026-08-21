param(
    [string]$Device = '192.168.1.23:5555'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Adb = 'C:\Android\platform-tools\adb.exe'
$Apk = Join-Path $ProjectRoot 'app\build\outputs\apk\debug\app-debug.apk'
$Gradle = Join-Path $ProjectRoot 'app\build.gradle'
$Package = 'pl.autoklinika.workshopventilation.hmi'

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

function Wait-ForHmiBoot {
    param(
        [string]$PreferredSerial,
        [int]$BootTimeoutSeconds = 120,
        [int]$AppTimeoutSeconds = 45
    )

    $bootDeadline = [DateTime]::UtcNow.AddSeconds($BootTimeoutSeconds)
    $bootSerial = $null

    Write-Host '[BOOT] Waiting for Android and ADB to return...'
    while ([DateTime]::UtcNow -lt $bootDeadline) {
        $ready = @(Get-ReadyAdbDevices)

        if (-not ($ready -contains $PreferredSerial)) {
            # A wireless transport normally disappears during reboot. Reconnect the
            # stable endpoint quietly until Android has brought adbd/network back.
            & $Adb connect $PreferredSerial 2>$null | Out-Null
            Start-Sleep -Seconds 2
            $ready = @(Get-ReadyAdbDevices)
        }

        if ($ready -contains $PreferredSerial) {
            $bootSerial = $PreferredSerial
        } elseif ($ready.Count -eq 1) {
            $bootSerial = $ready[0]
        } else {
            $bootSerial = $null
        }

        if ($bootSerial) {
            $bootCompleted = (& $Adb -s $bootSerial shell getprop sys.boot_completed 2>$null | Out-String).Trim()
            if ($LASTEXITCODE -eq 0 -and $bootCompleted -eq '1') {
                Write-Host "[BOOT] Android boot completed on $bootSerial" -ForegroundColor Green
                break
            }
        }

        Start-Sleep -Seconds 2
    }

    if (-not $bootSerial) {
        throw "HMI did not return to ADB within $BootTimeoutSeconds seconds after reboot."
    }

    $bootCompleted = (& $Adb -s $bootSerial shell getprop sys.boot_completed 2>$null | Out-String).Trim()
    if ($bootCompleted -ne '1') {
        throw "Android did not report sys.boot_completed=1 within $BootTimeoutSeconds seconds."
    }

    Write-Host '[BOOT] Waiting for kiosk HMI process to autostart...'
    $appDeadline = [DateTime]::UtcNow.AddSeconds($AppTimeoutSeconds)
    while ([DateTime]::UtcNow -lt $appDeadline) {
        $pid = (& $Adb -s $bootSerial shell pidof $Package 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $pid) {
            Write-Host "[BOOT] HMI autostart PASS; pid=$pid" -ForegroundColor Green
            return $bootSerial
        }
        Start-Sleep -Seconds 1
    }

    throw "Android booted, but $Package did not autostart within $AppTimeoutSeconds seconds."
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
Write-Host 'Policy:    full panel reboot is mandatory after every APK programming'
Write-Host

Write-Host '[1/7] Starting/checking ADB server...'
& $Adb start-server | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "ADB server failed with exit code $LASTEXITCODE"
}

Write-Host '[2/7] Looking for the iiyama ADB device...'
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

Write-Host '[3/7] Installing debug/test APK...'
& $Adb -s $Serial install -r -t $Apk | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "ADB install failed with exit code $LASTEXITCODE"
}

Write-Host '[4/7] Verifying installed APK version before reboot...'
$installed = Get-InstalledBuildVersion -Serial $Serial
Write-Host "Installed: versionCode $($installed.Code), versionName $($installed.Name)"
if ($installed.Code -ne $expected.Code -or $installed.Name -ne $expected.Name) {
    throw "STALE APK DETECTED. Source expects $($expected.Code)/$($expected.Name), but panel has $($installed.Code)/$($installed.Name). Re-run .\tools\build-debug.ps1 and deploy again."
}
Write-Host '[APK] Pre-reboot version verification: PASS' -ForegroundColor Green

Write-Host '[5/7] Rebooting the complete iiyama panel...'
& $Adb -s $Serial reboot
if ($LASTEXITCODE -ne 0) {
    throw "ADB reboot failed with exit code $LASTEXITCODE"
}

Write-Host '[6/7] Waiting for Android boot + automatic kiosk HMI start...'
$PostBootSerial = Wait-ForHmiBoot -PreferredSerial $Device

Write-Host '[7/7] Verifying installed APK version after reboot...'
$postBootInstalled = Get-InstalledBuildVersion -Serial $PostBootSerial
Write-Host "Installed after reboot: versionCode $($postBootInstalled.Code), versionName $($postBootInstalled.Name)"
if ($postBootInstalled.Code -ne $expected.Code -or $postBootInstalled.Name -ne $expected.Name) {
    throw "POST-REBOOT VERSION MISMATCH. Source expects $($expected.Code)/$($expected.Name), but panel has $($postBootInstalled.Code)/$($postBootInstalled.Name)."
}
Write-Host '[APK] Post-reboot version verification: PASS' -ForegroundColor Green

Write-Host
Write-Host 'Workshop Ventilation HMI installed, rebooted, autostarted and verified.' -ForegroundColor Green
