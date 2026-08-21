param(
    [string]$Device = "192.168.1.23:5555"
)

$ErrorActionPreference = "Stop"

$adb = "C:\Android\platform-tools\adb.exe"
$pkg = "pl.autoklinika.workshopventilation.hmi"
$activity = "$pkg/.MainActivity"
$action = "$pkg.LED_DIAGNOSTIC"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"
$projectRoot = Split-Path -Parent $PSScriptRoot
$gradle = Join-Path $projectRoot "app\build.gradle"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $PSScriptRoot "led-red-hardware-isolated-$timestamp.txt"

function Write-Log {
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
    $out = & $adb -s $Device shell "am broadcast -a $action --es state $State -p $pkg" 2>&1
    $out | ForEach-Object { Write-Log "ADB $_" }
    if ($LASTEXITCODE -ne 0) {
        throw "ADB diagnostic broadcast failed for $State"
    }
}

function Invoke-LedAtomicSequence {
    param([string[]]$Codes)

    $lines = @()
    foreach ($code in $Codes) {
        $lines += "echo w 0x$code > $sysfs"
    }
    $payload = ($lines -join "\n") + "\nexit\n"
    $remote = "printf '$payload' | su"

    $out = & $adb -s $Device shell $remote 2>&1
    if ($LASTEXITCODE -ne 0) {
        $out | ForEach-Object { Write-Log "ADB $_" }
        throw "LED write failed for sequence: $($Codes -join ',')"
    }
    Write-Log "WRITE atomic=$($Codes -join '+')"
}

function Ask-Result {
    param([string]$Label)

    Write-Host ""
    Write-Host "$Label"
    Write-Host "P = PASS   F = FAIL"
    while ($true) {
        $key = [Console]::ReadKey($true)
        switch ($key.KeyChar) {
            'p' { Write-Log "RESULT $Label PASS"; return $true }
            'P' { Write-Log "RESULT $Label PASS"; return $true }
            'f' { Write-Log "RESULT $Label FAIL"; return $false }
            'F' { Write-Log "RESULT $Label FAIL"; return $false }
        }
    }
}

function Run-RearmBlink {
    param(
        [int]$HalfPeriodMs,
        [int]$Cycles
    )

    Write-Log "TEST rearm-red-off halfPeriodMs=$HalfPeriodMs cycles=$Cycles"

    Invoke-LedAtomicSequence @("02")
    Start-Sleep -Milliseconds $HalfPeriodMs

    for ($i = 0; $i -lt $Cycles; $i++) {
        Invoke-LedAtomicSequence @("03", "04")
        Start-Sleep -Milliseconds $HalfPeriodMs
        Invoke-LedAtomicSequence @("02")
        Start-Sleep -Milliseconds $HalfPeriodMs
    }

    Invoke-LedAtomicSequence @("03", "04")
}

if (-not (Test-Path $adb)) {
    throw "ADB not found: $adb"
}

Write-Host "===== IIYAMA RED LED - PAUSED-RENDERER HARDWARE TEST ====="
Write-Host ""
Write-Host "WAŻNE: force-stop NIE izoluje tego HMI - Android/kiosk uruchamia proces ponownie."
Write-Host "Ten test używa debugowego PAUSE, który pozostawia proces i polling przy życiu,"
Write-Host "ale blokuje wszystkie fizyczne zapisy LED z HmiLedController."
Write-Host "Dopiero wtedy ręczne ADB -> su jest jedynym writerem LED."
Write-Host ""

& $adb connect $Device | Out-Host
Start-Sleep -Milliseconds 400
$state = (& $adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "Panel nie jest dostępny przez ADB. Stan: '$state'"
}
Write-Log "ADB connected device=$Device"

$expected = Get-ExpectedVersion
$installed = Get-InstalledVersion
Write-Log "VERSION source=$($expected.Code)/$($expected.Name) installed=$($installed.Code)/$($installed.Name)"
if ($installed.Code -ne $expected.Code -or $installed.Name -ne $expected.Name) {
    throw "STOP: potrzebny jest build $($expected.Code)/$($expected.Name), panel ma $($installed.Code)/$($installed.Name). Zbuduj i wgraj APK."
}

# Ensure Application/receiver is alive, then clear logs before PAUSE proof.
& $adb -s $Device shell "am start -n $activity" | Out-Null
Start-Sleep -Seconds 1
& $adb -s $Device logcat -c | Out-Null

$paused = $false
try {
    Write-Host "[1/6] PAUSE renderer LED aplikacji..."
    Send-DiagnosticState "PAUSE"
    Start-Sleep -Milliseconds 800

    $pauseLogs = (& $adb -s $Device logcat -d 2>&1 | Select-String -Pattern "WvcHmiLed.*renderer PAUSED" | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($pauseLogs)) {
        throw "STOP: brak potwierdzenia 'renderer PAUSED' w logcat. Nie wykonuję ręcznych zapisów LED."
    }
    $paused = $true
    Write-Log "PAUSE CONFIRMED"

    Write-Host "[2/6] Kontrola bazowa: OFF -> 0x03+0x05 GREEN..."
    Invoke-LedAtomicSequence @("02")
    Start-Sleep -Seconds 1
    Invoke-LedAtomicSequence @("03", "05")
    Start-Sleep -Seconds 2
    $greenRearm = Ask-Result "REARM_GREEN_03_PLUS_05"
    if (-not $greenRearm) {
        Write-Log "STOP greenRearm=False"
        throw "STOP: nawet przy potwierdzonym PAUSE nie działa 0x03+0x05."
    }

    Write-Host "[3/6] RED statyczny po re-arm: 0x03+0x04..."
    Invoke-LedAtomicSequence @("02")
    Start-Sleep -Milliseconds 500
    Invoke-LedAtomicSequence @("03", "04")
    Start-Sleep -Seconds 2
    $redStatic = Ask-Result "REARM_RED_STATIC_03_PLUS_04"
    if (-not $redStatic) {
        Write-Log "STOP redStatic=False"
        throw "STOP: czerwony statyczny nie działa po re-arm."
    }

    Write-Host "[4/6] RED blink 1000 ms ON / 1000 ms OFF..."
    Run-RearmBlink -HalfPeriodMs 1000 -Cycles 5
    $red1000 = Ask-Result "REARM_RED_BLINK_1000MS"

    Write-Host "[5/6] RED blink 500 ms ON / 500 ms OFF..."
    Run-RearmBlink -HalfPeriodMs 500 -Cycles 8
    $red500 = Ask-Result "REARM_RED_BLINK_500MS"

    Write-Host "[6/6] RED blink 250 ms ON / 250 ms OFF..."
    Run-RearmBlink -HalfPeriodMs 250 -Cycles 10
    $red250 = Ask-Result "REARM_RED_BLINK_250MS"

    Write-Log "SUMMARY greenRearm=$greenRearm redStatic=$redStatic red1000=$red1000 red500=$red500 red250=$red250"
}
finally {
    Write-Host ""
    Write-Host "===== RESTORE LIVE HMI LED CONTROL ====="
    if ($paused) {
        try {
            Send-DiagnosticState "CLEAR"
            Start-Sleep -Seconds 1
            Write-Log "CLEAR sent"
        } catch {
            Write-Warning "Nie udało się wysłać CLEAR: $($_.Exception.Message)"
        }
    }
}

Write-Host ""
Write-Host "Wynik zapisany w: $logFile"
Write-Host "===== KONIEC ====="
