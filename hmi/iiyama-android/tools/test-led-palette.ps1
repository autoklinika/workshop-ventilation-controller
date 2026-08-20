param(
    [string]$Device = "192.168.1.23:5555",
    [int]$DelaySeconds = 3
)

$ErrorActionPreference = "Stop"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"

Write-Host "===== IIYAMA RGB PALETTE TEST ====="
Write-Host "Device: $Device"
Write-Host "Delay:  $DelaySeconds s"
Write-Host ""
Write-Host "Potwierdzona paleta:"
Write-Host "  0x04 RED"
Write-Host "  0x05 GREEN"
Write-Host "  0x06 BLUE"
Write-Host "  0x07 WHITE"
Write-Host "  0x08 ORANGE"
Write-Host "  0x0B YELLOW"
Write-Host ""

Write-Host "===== ADB CONNECT ====="
$connect = adb connect $Device 2>&1
$connect | ForEach-Object { Write-Host $_ }
Start-Sleep -Milliseconds 500

$state = (adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device $Device nie jest dostępny. Aktualny stan: '$state'"
}
Write-Host "ADB: PASS"

$palette = @(
    @{ Code = "0x04"; Name = "RED" },
    @{ Code = "0x05"; Name = "GREEN" },
    @{ Code = "0x06"; Name = "BLUE" },
    @{ Code = "0x07"; Name = "WHITE" },
    @{ Code = "0x08"; Name = "ORANGE" },
    @{ Code = "0x0B"; Name = "YELLOW" }
)

foreach ($entry in $palette) {
    Write-Host "LED ON -> 0x03"
    adb -s $Device shell "printf 'echo w 0x03 > $sysfs\nexit\n' | su" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Nie udało się włączyć LED" }

    Write-Host "LED -> $($entry.Code) $($entry.Name)"
    adb -s $Device shell "printf 'echo w $($entry.Code) > $sysfs\nexit\n' | su" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Nie udało się ustawić $($entry.Name)" }
    Start-Sleep -Seconds $DelaySeconds
}

Write-Host "LED -> OFF (0x02)"
adb -s $Device shell "printf 'echo w 0x02 > $sysfs\nexit\n' | su" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Nie udało się wyłączyć LED" }

Write-Host "===== KONIEC TESTU ====="
