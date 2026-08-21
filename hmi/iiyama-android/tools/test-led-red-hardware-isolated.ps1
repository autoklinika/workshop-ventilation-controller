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

function Invoke-LedSequence {
    param([string[]]$Codes)

    $commands = @()
    foreach ($code in $Codes) {
        $commands += "echo w 0x$code > $sysfs"
    }
    $payload = ($commands -join "`n") + "`nexit`n"
    $escaped = $payload.Replace("'", "'\"'\"'")

    $out = & $adb -s $Device shell "printf '$escaped' | su" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $out | ForEach-Object { Write-Log "ADB $_" }
        throw "LED write failed for sequence: $($Codes -join ',')"
    }

    Write-Log "WRITE sequence=$($Codes -join ',')"
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

function Run-DirectBlink {
    param(
        [int]$HalfPeriodMs,
        [int]$Cycles
    )

    Write-Log "TEST direct-red-off halfPeriodMs=$HalfPeriodMs cycles=$Cycles"
    for ($i = 0; $i -lt $Cycles; $i++) {
        Invoke-LedSequence @("04")
        Start-Sleep -Milliseconds $HalfPeriodMs
        Invoke-LedSequence @("02")
        Start-Sleep -Milliseconds $HalfPeriodMs
    }
    Invoke-LedSequence @("04")
}

function Run-LegacyBlink {
    param(
        [int]$HalfPeriodMs,
        [int]$Cycles
    )

    Write-Log "TEST legacy-off-on-red halfPeriodMs=$HalfPeriodMs cycles=$Cycles"
    for ($i = 0; $i -lt $Cycles; $i++) {
        Invoke-LedSequence @("03", "04")
        Start-Sleep -Milliseconds $HalfPeriodMs
        Invoke-LedSequence @("02")
        Start-Sleep -Milliseconds $HalfPeriodMs
    }
    Invoke-LedSequence @("04")
}

if (-not (Test-Path $adb)) {
    throw "ADB not found: $adb"
}

Write-Host "===== IIYAMA RED LED - ISOLATED HARDWARE TEST ====="
Write-Host ""
Write-Host "Ten test zatrzymuje HMI, więc aplikacja NIE może pisać do LED równolegle."
Write-Host "Sterowanie idzie dokładnie przez ADB -> su -> vendor sysfs."
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
    Write-Host "[1/6] Force-stop HMI - usuwamy wszystkie zapisy aplikacji do LED..."
    & $adb -s $Device shell am force-stop $pkg | Out-Null
    Start-Sleep -Seconds 1

    Write-Host "[2/6] Statyczny czerwony - dokładnie 0x04..."
    Invoke-LedSequence @("04")
    Start-Sleep -Seconds 2
    $staticRedOk = Ask-Result "STATIC_RED_0x04"

    Write-Host "[3/6] OFF - dokładnie 0x02..."
    Invoke-LedSequence @("02")
    Start-Sleep -Seconds 2
    $offOk = Ask-Result "OFF_0x02"

    if (-not $staticRedOk -or -not $offOk) {
        Write-Log "STOP staticRedOk=$staticRedOk offOk=$offOk"
        throw "STOP: nie ma sensu testować migania, dopóki osobno 0x04 RED i 0x02 OFF nie działają poprawnie."
    }

    Write-Host "[4/6] DIRECT blink 1000 ms RED / 1000 ms OFF..."
    Run-DirectBlink -HalfPeriodMs 1000 -Cycles 5
    $direct1000 = Ask-Result "DIRECT_BLINK_1000MS"

    Write-Host "[5/6] DIRECT blink 500 ms RED / 500 ms OFF..."
    Run-DirectBlink -HalfPeriodMs 500 -Cycles 8
    $direct500 = Ask-Result "DIRECT_BLINK_500MS"

    Write-Host "[6/6] DIRECT blink 250 ms RED / 250 ms OFF..."
    Run-DirectBlink -HalfPeriodMs 250 -Cycles 10
    $direct250 = Ask-Result "DIRECT_BLINK_250MS"

    if (-not $direct500) {
        Write-Host ""
        Write-Host "Porównanie: stara sekwencja OFF -> (0x03 ON + 0x04 RED), 500 ms..."
        Run-LegacyBlink -HalfPeriodMs 500 -Cycles 8
        $legacy500 = Ask-Result "LEGACY_BLINK_500MS"
        Write-Log "SUMMARY direct1000=$direct1000 direct500=$direct500 direct250=$direct250 legacy500=$legacy500"
    } else {
        Write-Log "SUMMARY direct1000=$direct1000 direct500=$direct500 direct250=$direct250 legacy500=NOT_RUN"
    }
}
finally {
    Write-Host ""
    Write-Host "===== RESTORE HMI ====="
    try {
        Invoke-LedSequence @("05")
    } catch {
        Write-Warning "Nie udało się ustawić zielonego baseline: $($_.Exception.Message)"
    }

    & $adb -s $Device shell am start -W -n $activity | Out-Host
    Write-Log "HMI restart requested"
}

Write-Host ""
Write-Host "Wynik zapisany w: $logFile"
Write-Host "===== KONIEC ====="
