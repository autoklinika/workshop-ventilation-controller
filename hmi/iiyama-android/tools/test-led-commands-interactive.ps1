param(
    [string]$Device = "192.168.1.23:5555"
)

$ErrorActionPreference = "Stop"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"

function Invoke-AdbChecked {
    param([string]$RemoteCommand)
    & adb -s $Device shell $RemoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "ADB command failed: $RemoteCommand"
    }
}

function Set-LedCommand {
    param([string]$Hex)
    Invoke-AdbChecked "printf 'echo w $Hex > $sysfs\nexit\n' | su"
}

Write-Host "===== IIYAMA INTERACTIVE LED COMMAND SCAN ====="
Write-Host "Device: $Device"
Write-Host "Każda komenda pozostaje aktywna tak długo, aż naciśniesz ENTER."
Write-Host "Przed każdym kolejnym testem robimy OFF -> ON, żeby wyczyścić poprzedni efekt."
Write-Host ""

Write-Host "===== ADB CONNECT ====="
adb connect $Device | Out-Host
if ($LASTEXITCODE -ne 0) { throw "adb connect failed" }

$state = (adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device $Device nie jest dostępny. Stan: '$state'"
}
Write-Host "ADB: PASS"

$commands = 0x08..0x17

foreach ($value in $commands) {
    $hex = "0x{0:X2}" -f $value

    Write-Host ""
    Write-Host "----------------------------------------"
    Write-Host "RESET: OFF -> ON"
    Set-LedCommand "0x02"
    Start-Sleep -Milliseconds 300
    Set-LedCommand "0x03"
    Start-Sleep -Milliseconds 500

    Write-Host "TEST: $hex"
    Set-LedCommand $hex
    Write-Host "Obserwuj pasek. ENTER = następna komenda."
    [void](Read-Host)
}

Write-Host ""
Write-Host "LED -> OFF"
Set-LedCommand "0x02"
Write-Host "===== KONIEC TESTU ====="
