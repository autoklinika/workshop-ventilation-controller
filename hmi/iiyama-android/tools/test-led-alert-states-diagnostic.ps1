param(
    [string]$Device = "192.168.1.23:5555"
)

$ErrorActionPreference = "Stop"

$adb = "C:\Android\platform-tools\adb.exe"
$pkg = "pl.autoklinika.workshopventilation.hmi"
$activity = "$pkg/.MainActivity"
$action = "$pkg.LED_DIAGNOSTIC"
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
    @{ State = "CRITICAL_UNACK";     Expected = "RED fast blink" },
    @{ State = "CRITICAL_ACK";       Expected = "RED solid" },
    @{ State = "COMMUNICATION_LOST"; Expected = "RED very fast blink" },
    @{ State = "STARTUP_UNKNOWN";    Expected = "WHITE slow blink" },
    @{ State = "SERVICE";            Expected = "BLUE solid" }
)

function Write-ResultLine {
    param([string]$Text)
    $line = "$(Get-Date -Format 'HH:mm:ss.fff')  $Text"
    $line | Tee-Object -FilePath $logFile -Append | Write-Host
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

Write-Host "===== IIYAMA ALERT LED - DETERMINISTIC DIAGNOSTIC ====="
Write-Host ""
Write-Host "Ten test NIE zmienia alertów na CM5."
Write-Host "Aplikacja nadal je odpytuje, ale LED jest chwilowo sterowany przez debug override."
Write-Host "Nie uruchamiaj równolegle żadnego innego skryptu LED/sysfs."
Write-Host ""

& $adb connect $Device | Out-Host
Start-Sleep -Milliseconds 500
$state = (& $adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "Panel nie jest dostępny przez ADB. Stan: '$state'"
}

Write-ResultLine "ADB connected device=$Device"

# Start/bring up the HMI so the debug receiver is registered.
& $adb -s $Device shell "am start -n $activity" | Out-Null
Start-Sleep -Seconds 2

# Clear old LED logs so every observed transition belongs to this run.
& $adb -s $Device logcat -c | Out-Null

# Put the controller into a known static baseline first. This also replaces any
# vendor animation/effect left behind by earlier manual experiments.
Send-DiagnosticState "NORMAL"
Start-Sleep -Seconds 2

$aborted = $false

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

Write-Host ""
Write-Host "===== RESTORE LIVE ALERT CONTROL ====="
Send-DiagnosticState "CLEAR"
Start-Sleep -Seconds 1

Write-Host ""
Write-Host "===== WvcHmiLed LOGS FROM THIS RUN ====="
$ledLogs = & $adb -s $Device logcat -d 2>&1 | Select-String -Pattern "WvcHmiLed"
$ledLogs | ForEach-Object {
    $_.Line | Tee-Object -FilePath $logFile -Append | Write-Host
}

Write-Host ""
Write-Host "Wynik zapisany w: $logFile"
Write-Host "===== KONIEC ====="
