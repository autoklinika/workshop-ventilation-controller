param(
    [string]$Device = "192.168.1.23:5555"
)

$ErrorActionPreference = "Stop"
$adb = "C:\Android\platform-tools\adb.exe"
$sysfs = "/sys/devices/platform/led_con_h/zigbee_reset"

function Send-LedCode {
    param([string]$Code)

    Write-Host "  -> $Code"
    & $adb -s $Device shell "printf 'echo w $Code > $sysfs\nexit\n' | su" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udało się wysłać $Code"
    }
}

function Get-CustomRgbCode {
    param(
        [int]$Red,
        [int]$Green,
        [int]$Blue
    )

    if ($Red -lt 0 -or $Red -gt 255 -or
        $Green -lt 0 -or $Green -gt 255 -or
        $Blue -lt 0 -or $Blue -gt 255) {
        throw "RGB musi być w zakresie 0..255"
    }

    return ("0x66{0:X2}{1:X2}{2:X2}" -f $Red, $Green, $Blue)
}

function Send-CustomRgb {
    param(
        [int]$Red,
        [int]$Green,
        [int]$Blue
    )

    Send-LedCode (Get-CustomRgbCode $Red $Green $Blue)
}

function Test-CustomColor {
    param(
        [string]$Name,
        [int]$Red,
        [int]$Green,
        [int]$Blue
    )

    Write-Host ""
    Write-Host "========================================"
    Write-Host "$Name  RGB($Red,$Green,$Blue)"
    Write-Host "========================================"

    Send-CustomRgb $Red $Green $Blue
    Read-Host "Sprawdź kolor. ENTER = test FADE OUT / IN"

    # Software fade based on the vendor-documented custom command 0x66RRGGBB.
    # We deliberately do NOT use vendor effect 0x0F because it always selects
    # its own white STROBE/FADE presentation instead of fading the current colour.
    $levels = @(255, 224, 192, 160, 128, 96, 64, 32, 8, 0, 8, 32, 64, 96, 128, 160, 192, 224, 255)

    foreach ($level in $levels) {
        $r = [int][math]::Round($Red * $level / 255.0)
        $g = [int][math]::Round($Green * $level / 255.0)
        $b = [int][math]::Round($Blue * $level / 255.0)
        Send-CustomRgb $r $g $b
        Start-Sleep -Milliseconds 90
    }

    Read-Host "Czy kolor płynnie wygasł i wrócił bez przejścia na biały? ENTER = dalej"
}

Write-Host "===== IIYAMA: CUSTOM RGB 0x66RRGGBB + SOFTWARE FADE ====="
Write-Host "Dokumentacja producenta podaje format: 0x66RRGGBB (RR/GG/BB = 0..255)."

& $adb connect $Device | Out-Host
Start-Sleep -Milliseconds 500
$state = (& $adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device $Device niedostępny. Stan: '$state'"
}

Send-LedCode "0x02"
Start-Sleep -Milliseconds 300
Send-LedCode "0x03"
Start-Sleep -Milliseconds 300

Test-CustomColor "CZERWONY" 255 0 0
Test-CustomColor "POMARAŃCZOWY" 255 128 0
Test-CustomColor "ŻÓŁTY" 255 255 0

Write-Host ""
Write-Host "LED OFF"
Send-LedCode "0x02"
Write-Host "===== KONIEC ====="
