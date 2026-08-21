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

# Vendor documentation describes a full NEC form 0x00F7XXXX.
# For a key byte K, this probe uses K followed by its NEC complement (~K):
#   key 0x00 -> 0x00F700FF  (brightness + candidate)
#   key 0x01 -> 0x00F701FE  (brightness - candidate)
#   key 0x04 -> 0x00F704FB  (RED validation candidate)
$NEC_BRIGHT_PLUS  = "0x00F700FF"
$NEC_BRIGHT_MINUS = "0x00F701FE"
$NEC_RED          = "0x00F704FB"

Write-Host "===== IIYAMA: FULL NEC BRIGHTNESS PROBE ====="
Write-Host "Ten test nie zakłada, że kody są poprawne — ma to zweryfikować sprzęt."
Write-Host ""

& $adb connect $Device | Out-Host
Start-Sleep -Milliseconds 500
$state = (& $adb -s $Device get-state 2>&1 | Out-String).Trim()
if ($state -ne "device") {
    throw "ADB device $Device niedostępny. Stan: '$state'"
}

Write-Host "1) Ustawiam statyczny BIAŁY zwykłym, potwierdzonym kodem 0x07."
Send-LedCode "0x02"
Start-Sleep -Milliseconds 300
Send-LedCode "0x03"
Start-Sleep -Milliseconds 300
Send-LedCode "0x07"
Read-Host "Sprawdź biały. ENTER = test pełnego NEC RED"

Write-Host ""
Write-Host "2) Test pełnego NEC dla RED: $NEC_RED"
Send-LedCode $NEC_RED
Read-Host "Czy pasek zrobił się CZERWONY? Zapamiętaj wynik. ENTER = test jasności -"

Write-Host ""
Write-Host "3) Ustawiam zwykły czerwony 0x04 jako pewny punkt startowy."
Send-LedCode "0x04"
Start-Sleep -Milliseconds 300
Write-Host "Naciskaj '-' żeby wysłać pełny NEC brightness minus, '+' dla plus."
Write-Host "R = reset do pełnego czerwonego 0x04, Q = koniec."

while ($true) {
    $key = [Console]::ReadKey($true)
    switch ($key.KeyChar) {
        '-' {
            Write-Host "BRIGHTNESS -"
            Send-LedCode $NEC_BRIGHT_MINUS
        }
        '+' {
            Write-Host "BRIGHTNESS +"
            Send-LedCode $NEC_BRIGHT_PLUS
        }
        'r' {
            Write-Host "RESET RED"
            Send-LedCode "0x04"
        }
        'R' {
            Write-Host "RESET RED"
            Send-LedCode "0x04"
        }
        'q' { break }
        'Q' { break }
    }
}

Write-Host ""
Write-Host "LED OFF"
Send-LedCode "0x02"
Write-Host "===== KONIEC ====="
