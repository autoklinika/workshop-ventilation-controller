param(
    [string]$Device = "192.168.1.23:5555",
    [int]$DelaySeconds = 3
)

$ErrorActionPreference = "Stop"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"

Write-Host "===== IIYAMA RGB PALETTE TEST 0x08..0x17 ====="
Write-Host "Device: $Device"
Write-Host "Delay:  $DelaySeconds s"
Write-Host ""
Write-Host "Zanotuj, który kod daje ŻÓŁTY i który POMARAŃCZOWY."
Write-Host ""

adb -s $Device get-state | Out-Null

foreach ($value in 0x08..0x17) {
    $hex = "0x{0:X2}" -f $value
    Write-Host "LED -> $hex"
    adb -s $Device shell "printf 'echo w $hex > $sysfs\nexit\n' | su"
    Start-Sleep -Seconds $DelaySeconds
}

Write-Host "LED -> OFF (0x02)"
adb -s $Device shell "printf 'echo w 0x02 > $sysfs\nexit\n' | su"

Write-Host "===== KONIEC TESTU ====="
