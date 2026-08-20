param(
    [string]$Device = "192.168.1.23:5555",
    [int]$DelaySeconds = 3
)

$ErrorActionPreference = "Stop"
$adb = "C:\Android\platform-tools\adb.exe"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"

Write-Host "===== IIYAMA STATIC LED PALETTE TEST ====="
Write-Host "Device: $Device"
Write-Host "Delay:  $DelaySeconds s"
Write-Host ""
Write-Host "Potwierdzone statyczne komendy:"
Write-Host "  0x02 OFF"
Write-Host "  0x03 ON"
Write-Host "  0x04 RED"
Write-Host "  0x05 GREEN"
Write-Host "  0x06 BLUE"
Write-Host "  0x07 WHITE"
Write-Host "  0x08 ORANGE"
Write-Host "  0x10 YELLOW"
Write-Host ""
Write-Host "Efekty 0x0B/0x0F/0x13/0x17 nie są używane w AlertV2."
Write-Host ""

Write-Host "===== ADB CONNECT ====="
$connect = & $adb connect $Device 2>&1
$connect | ForEach-Object { Write-Host $_ }
Start-Sleep -Milliseconds 500

$state = (& $adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device $Device nie jest dostępny. Aktualny stan: '$state'"
}
Write-Host "ADB: PASS"

function Send-Led {
    param([string]$Code)

    & $adb -s $Device shell "printf 'echo w $Code > $sysfs\nexit\n' | su" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udało się wysłać komendy $Code"
    }
}

Write-Host "LED ON -> 0x03"
Send-Led "0x03"
Start-Sleep -Milliseconds 200

$staticColors = @(
    @{ Code = "0x05"; Name = "GREEN / NORMAL" },
    @{ Code = "0x06"; Name = "BLUE / INFO-SERVICE" },
    @{ Code = "0x10"; Name = "YELLOW / WARNING" },
    @{ Code = "0x08"; Name = "ORANGE / ALARM" },
    @{ Code = "0x04"; Name = "RED / CRITICAL" },
    @{ Code = "0x07"; Name = "WHITE / STARTUP-UNKNOWN" }
)

foreach ($entry in $staticColors) {
    Write-Host "LED -> $($entry.Code) $($entry.Name)"
    Send-Led $entry.Code
    Start-Sleep -Seconds $DelaySeconds
}

Write-Host "LED -> OFF (0x02)"
Send-Led "0x02"

Write-Host "===== KONIEC TESTU ====="
