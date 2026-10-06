param(
    [string]$Device = "192.168.1.23:5555",
    [switch]$RedOnly
)

$ErrorActionPreference = "Stop"

$adb = "C:\Android\platform-tools\adb.exe"
$pkg = "pl.autoklinika.workshopventilation.hmi"
$activity = "$pkg/.MainActivity"
$action = "$pkg.LED_DIAGNOSTIC"
$projectRoot = Split-Path -Parent $PSScriptRoot
$gradle = Join-Path $projectRoot "app\build.gradle"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $PSScriptRoot "led-alert-diagnostic-$timestamp.txt"

$tests = @(
    @{ State = "NORMAL";             Expected = "GREEN solid" },
    @{ State = "INFO_UNACK";         Expected = "BLUE slow blink" },
    @{ State = "INFO_ACK";           Expected = "BLUE solid" },
    @{ State = "WARNING_UNACK";      Expected = "YELLOW blink" },
    @{ State = "WARNING_ACK";        Expected = "YELLOW solid" },
    @{ State = "ALARM_UNACK";        Expected = "ORANGE blink" },
    @{ State = "ALARM_ACK";          Expected = "ORANGE solid" },
    @{ State = "CRITICAL_UNACK";     Expected = "RED blink: 500 ms ON / 500 ms OFF" },
    @{ State = "CRITICAL_ACK";       Expected = "RED solid" },
    @{ State = "COMMUNICATION_LOST"; Expected = "RED blink: 500 ms ON / 500 ms OFF" },
    @{ State = "STARTUP_UNKNOWN";    Expected = "WHITE slow blink" },
    @{ State = "SERVICE";            Expected = "BLUE solid" }
)

if ($RedOnly) {
    $tests = @(
        @{ State = "CRITICAL_UNACK";     Expected = "RED blink: 500 ms ON / 500 ms OFF" },
        @{ State = "CRITICAL_ACK";       Expected = "RED solid" },
        @{ State = "COMMUNICATION_LOST"; Expected = "RED blink: 500 ms ON / 500 ms OFF" }
    )
}

function Write-ResultLine {
    param([string]$Text)
    $line = "$(Get-Date -Format 'HH:mm:ss.fff')  $Text"
    $line | Tee-Object -FilePath $logFile -Append | Write-Host
}

function Get-ExpectedVersion {
    $text = Get-Content -Raw $gradle
    $nameMatch = [regex]::Match($text, "versionName\s*=\s*'([^']+)'")
    $codeMatch = [regex]::Match($text, 'versionCode\s*=\s*(\d+)')
    if (-not $nameMatch.Success -or -not $codeMatch.Success) {
        throw "Nie można odczytać versionName/versionCode z $gradle"
    }
    [pscustomobject]@{
        Name = $nameMatch.Groups[1].Value
        Code = [int]$codeMatch.Groups[1].Value
    }
}

function Get-InstalledVersion {
    $dump = (& $adb -s $Device shell dumpsys package $pkg 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "Nie można odczytać metadanych zainstalowanego pakietu $pkg"
    }
    $nameMatch = [regex]::Match($dump, 'versionName=([^\r\n\s]+)')
    $codeMatch = [regex]::Match($dump, 'versionCode=(\d+)')
    if (-not $nameMatch.Success -or -not $codeMatch.Success) {
        throw "Nie można odczytać wersji zainstalowanego HMI"
    }
    [pscustomobject]@{
        Name = $nameMatch.Groups[1].Value.Trim()
        Code = [int]$codeMatch.Groups[1].Value
    }
}

function Send-DiagnosticState {
    param([string]$State)

    Write-ResultLine "SEND state=$State"
    $output = & $adb -s $Device shell "am broadcast -a $action --es state $State -p $pkg" 2>&1
    $output | ForEach-Object { Write-ResultLine "ADB  $_" }
    if ($LASTEXITCODE -ne 0) {
        throw "ADB broadcast failed for state $State"
    }
    Start-Sleep -Milliseconds 750
}

function Restore-LiveControl {
    try {
        Write-Host ""
        Write-Host "===== RESTORE LIVE ALERT CONTROL ====="
        Send-DiagnosticState "CLEAR"
        Start-Sleep -Seconds 1
    } catch {
        Write-Warning "Nie udało się automatycznie wysłać CLEAR: $($_.Exception.Message)"
    }
}

Write-Host "===== IIYAMA ALERT LED - DETERMINISTIC DIAGNOSTIC ====="
Write-Host ""
Write-Host "Ten test NIE zmienia alertów na CM5."
Write-Host "Aplikacja nadal je odpytuje, ale LED jest chwilowo sterowany przez debug override."
Write-Host "Nie uruchamiaj równolegle żadnego innego skryptu LED/sysfs."
if ($RedOnly) {
    Write-Host "Tryb: RED ONLY (CRITICAL_UNACK / CRITICAL_ACK / COMMUNICATION_LOST)"
}
Write-Host ""

& $adb connect $Device | Out-Host
Start-Sleep -Milliseconds 500
$state = (& $adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "Panel nie jest dostępny przez ADB. Stan: '$state'"
}

Write-ResultLine "ADB connected device=$Device"

$expected = Get-ExpectedVersion
$installed = Get-InstalledVersion
Write-ResultLine "VERSION source=$($expected.Code)/$($expected.Name) installed=$($installed.Code)/$($installed.Name)"
if ($installed.Code -ne $expected.Code -or $installed.Name -ne $expected.Name) {
    throw "STOP: na panelu jest STARA WERSJA APK. Źródła: $($expected.Code)/$($expected.Name), panel: $($installed.Code)/$($installed.Name). Uruchom .\tools\build-debug.ps1 i .\tools\deploy-debug.ps1."
}
Write-Host "Wersja APK: PASS ($($installed.Code) / $($installed.Name))" -ForegroundColor Green

& $adb -s $Device shell "am start -n $activity" | Out-Null
Start-Sleep -Seconds 2

& $adb -s $Device logcat -c | Out-Null

Send-DiagnosticState "NORMAL"
Start-Sleep -Seconds 2

$aborted = $false

try {
    foreach ($test in $tests) {
        if ($aborted) { break }

        Write-Host ""
        Write-Host "============================================================"
        Write-Host "STATE:    $($test.State)"
        Write-Host "EXPECTED: $($test.Expected)"
        Write-Host "============================================================"

        Send-DiagnosticState $test.State

        Write-Host "Obserwuj pasek minimum kilka pełnych cykli."
        Write-Host "P = PASS   F = FAIL   Q = przerwij"

        while ($true) {
            $key = [Console]::ReadKey($true)
            switch ($key.KeyChar) {
                'p' { Write-ResultLine "RESULT state=$($test.State) PASS expected='$($test.Expected)'"; break }
                'P' { Write-ResultLine "RESULT state=$($test.State) PASS expected='$($test.Expected)'"; break }
                'f' { Write-ResultLine "RESULT state=$($test.State) FAIL expected='$($test.Expected)'"; break }
                'F' { Write-ResultLine "RESULT state=$($test.State) FAIL expected='$($test.Expected)'"; break }
                'q' { Write-ResultLine "ABORT state=$($test.State)"; $aborted = $true; break }
                'Q' { Write-ResultLine "ABORT state=$($test.State)"; $aborted = $true; break }
                default { continue }
            }
            break
        }
    }
} finally {
    Restore-LiveControl
}

Write-Host ""
Write-Host "===== WvcHmiLed LOGS FROM THIS RUN ====="
$ledLogs = & $adb -s $Device logcat -d 2>&1 | Select-String -Pattern "WvcHmiLed"
$ledLogs | ForEach-Object {
    $_.Line | Tee-Object -FilePath $logFile -Append | Write-Host
}

Write-Host ""
Write-Host "Wynik zapisany w: $logFile"
Write-Host "===== KONIEC ====="
