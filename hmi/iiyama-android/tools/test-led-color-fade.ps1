param(
    [string]$Device = "192.168.1.23:5555"
)

$ErrorActionPreference = "Stop"
$adb = "C:\Android\platform-tools\adb.exe"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"

function Send-Led {
    param([string]$Code)
    Write-Host "  -> $Code"
    & $adb -s $Device shell "printf 'echo w $Code > $sysfs\nexit\n' | su" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udało się wysłać $Code"
    }
}

function Test-ColorFade {
    param(
        [string]$ColorCode,
        [string]$ColorName
    )

    Write-Host ""
    Write-Host "========================================"
    Write-Host "$ColorName [$ColorCode] -> FADE [0x0F]"
    Write-Host "========================================"

    Send-Led "0x02"
    Start-Sleep -Milliseconds 500
    Send-Led "0x03"
    Start-Sleep -Milliseconds 300
    Send-Led $ColorCode

    Write-Host ""
    Write-Host "Najpierw obejrzyj kolor statyczny."
    Read-Host "ENTER = uruchom 0x0F"

    Send-Led "0x0F"
    Write-Host ""
    Write-Host "Obserwuj czy FADE zachowuje $ColorName, czy przechodzi na biały."
    Read-Host "ENTER = następny test"
}

Write-Host "===== IIYAMA: CZY 0x0F FADE ZACHOWUJE AKTUALNY KOLOR? ====="

& $adb connect $Device | Out-Host
Start-Sleep -Milliseconds 500
$state = (& $adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device $Device niedostępny. Stan: '$state'"
}

Test-ColorFade "0x04" "CZERWONY"
Test-ColorFade "0x08" "POMARAŃCZOWY"
Test-ColorFade "0x10" "ŻÓŁTY"

Write-Host ""
Write-Host "LED OFF"
Send-Led "0x02"
Write-Host "===== KONIEC ====="
