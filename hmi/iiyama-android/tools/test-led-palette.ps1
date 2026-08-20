param(
    [string]$Device = "192.168.1.23:5555",
    [int]$DelaySeconds = 3
)

$ErrorActionPreference = "Stop"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"

Write-Host "===== IIYAMA STATIC LED COMMAND TEST ====="
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
Write-Host ""
Write-Host "UWAGA: 0x08..0x17 nie są traktowane jako paleta kolorów."
Write-Host "Wcześniejsze testy wykazały w tym zakresie tryby/efekty animowane."
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

Write-Host "LED ON -> 0x03"
adb -s $Device shell "printf 'echo w 0x03 > $sysfs\nexit\n' | su" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Nie udało się włączyć LED" }
Start-Sleep -Milliseconds 200

$staticColors = @(
    @{ Code = "0x04"; Name = "RED" },
    @{ Code = "0x05"; Name = "GREEN" },
    @{ Code = "0x06"; Name = "BLUE" },
    @{ Code = "0x07"; Name = "WHITE" }
)

foreach ($entry in $staticColors) {
    Write-Host "LED -> $($entry.Code) $($entry.Name)"
    adb -s $Device shell "printf 'echo w $($entry.Code) > $sysfs\nexit\n' | su" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Nie udało się ustawić $($entry.Name)" }
    Start-Sleep -Seconds $DelaySeconds
}

Write-Host "LED -> OFF (0x02)"
adb -s $Device shell "printf 'echo w 0x02 > $sysfs\nexit\n' | su" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Nie udało się wyłączyć LED" }

Write-Host "===== KONIEC TESTU ====="
