param(
    [string]$Device = "192.168.1.23:5555",
    [int]$DelaySeconds = 3
)

$ErrorActionPreference = "Stop"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"

function Invoke-AdbChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & adb @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "ADB failed ($LASTEXITCODE): adb $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }
    return $output
}

Write-Host "===== IIYAMA RGB PALETTE TEST 0x08..0x17 ====="
Write-Host "Device: $Device"
Write-Host "Delay:  $DelaySeconds s"
Write-Host ""
Write-Host "Zanotuj, który kod daje ŻÓŁTY i który POMARAŃCZOWY."
Write-Host ""

if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    throw "Nie znaleziono adb w PATH."
}

Write-Host "===== ADB CONNECT ====="
$connect = & adb connect $Device 2>&1
$connectCode = $LASTEXITCODE
$connect | ForEach-Object { Write-Host $_ }
if ($connectCode -ne 0) {
    throw "Nie udało się połączyć ADB z $Device. Sprawdź IP panelu i czy Wireless debugging / adb tcpip jest aktywne."
}

$state = Invoke-AdbChecked -Arguments @('-s', $Device, 'get-state')
if (($state -join '').Trim() -ne 'device') {
    throw "ADB widzi $Device, ale stan nie jest 'device': $($state -join ' ')"
}

Write-Host "ADB: PASS"
Write-Host ""

foreach ($value in 0x08..0x17) {
    $hex = "0x{0:X2}" -f $value
    Write-Host "LED -> $hex"
    Invoke-AdbChecked -Arguments @(
        '-s', $Device,
        'shell',
        "printf 'echo w $hex > $sysfs\nexit\n' | su"
    ) | Out-Null
    Start-Sleep -Seconds $DelaySeconds
}

Write-Host "LED -> OFF (0x02)"
Invoke-AdbChecked -Arguments @(
    '-s', $Device,
    'shell',
    "printf 'echo w 0x02 > $sysfs\nexit\n' | su"
) | Out-Null

Write-Host "===== KONIEC TESTU ====="
