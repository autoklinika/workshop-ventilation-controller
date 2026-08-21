param(
    [string]$Device = "192.168.1.23:5555"
)

$ErrorActionPreference = "Stop"

$adb = "C:\Android\platform-tools\adb.exe"
$pkg = "pl.autoklinika.workshopventilation.hmi"
$activity = "$pkg/.MainActivity"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $PSScriptRoot "led-red-hardware-isolated-$timestamp.txt"

function Write-Log {
    param([string]$Text)
    $line = "$(Get-Date -Format 'HH:mm:ss.fff')  $Text"
    $line | Tee-Object -FilePath $logFile -Append | Write-Host
}

function Invoke-LedAtomicSequence {
    param([string[]]$Codes)

    $lines = @()
    foreach ($code in $Codes) {
        $lines += "echo w 0x$code > $sysfs"
    }

    # Keep all commands in ONE su session. This is important on the B3:
    # after 0x02 OFF, 0x03 wakes the controller to white and the colour command
    # must follow immediately in the same shell to re-arm the requested colour.
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

    # Start from a known OFF latch.
    Invoke-LedAtomicSequence @("02")
    Start-Sleep -Milliseconds $HalfPeriodMs

    for ($i = 0; $i -lt $Cycles; $i++) {
        # Hardware-proven re-arm: ON + RED in the SAME su session.
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

Write-Host "===== IIYAMA RED LED - ISOLATED RE-ARM TEST ====="
Write-Host ""
Write-Host "Potwierdzony mechanizm B3:"
Write-Host "  0x02       = OFF latch"
Write-Host "  0x03       = wake/default WHITE"
Write-Host "  0x03+COLOR = wake + kolor, w jednej sesji su"
Write-Host ""
Write-Host "Test zatrzymuje HMI, więc aplikacja nie może pisać do LED równolegle."
Write-Host "Na końcu HMI zostanie uruchomione ponownie."
Write-Host ""

& $adb connect $Device | Out-Host
Start-Sleep -Milliseconds 400
$state = (& $adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "Panel nie jest dostępny przez ADB. Stan: '$state'"
}

Write-Log "ADB connected device=$Device"

try {
    Write-Host "[1/5] Force-stop HMI..."
    & $adb -s $Device shell am force-stop $pkg | Out-Null
    Start-Sleep -Seconds 1

    Write-Host "[2/5] Kontrola re-arm: OFF -> ON+GREEN w jednej sesji..."
    Invoke-LedAtomicSequence @("02")
    Start-Sleep -Seconds 1
    Invoke-LedAtomicSequence @("03", "05")
    Start-Sleep -Seconds 2
    $greenRearm = Ask-Result "REARM_GREEN_03_PLUS_05"
    if (-not $greenRearm) {
        Write-Log "STOP greenRearm=False"
        throw "STOP: nie potwierdzono bazowego re-arm 0x03+0x05."
    }

    Write-Host "[3/5] RED blink: 1000 ms ON / 1000 ms OFF..."
    Run-RearmBlink -HalfPeriodMs 1000 -Cycles 5
    $red1000 = Ask-Result "REARM_RED_BLINK_1000MS"

    Write-Host "[4/5] RED blink: 500 ms ON / 500 ms OFF..."
    Run-RearmBlink -HalfPeriodMs 500 -Cycles 8
    $red500 = Ask-Result "REARM_RED_BLINK_500MS"

    Write-Host "[5/5] RED blink: 250 ms ON / 250 ms OFF..."
    Run-RearmBlink -HalfPeriodMs 250 -Cycles 10
    $red250 = Ask-Result "REARM_RED_BLINK_250MS"

    Write-Log "SUMMARY greenRearm=$greenRearm red1000=$red1000 red500=$red500 red250=$red250"
}
finally {
    Write-Host ""
    Write-Host "===== RESTORE HMI ====="
    try {
        Invoke-LedAtomicSequence @("03", "05")
    } catch {
        Write-Warning "Nie udało się ustawić zielonego baseline: $($_.Exception.Message)"
    }

    & $adb -s $Device shell am start -W -n $activity | Out-Host
    Write-Log "HMI restart requested"
}

Write-Host ""
Write-Host "Wynik zapisany w: $logFile"
Write-Host "===== KONIEC ====="
