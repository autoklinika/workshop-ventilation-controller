$ErrorActionPreference = 'Stop'

$target = Join-Path $PSScriptRoot '..\service-access.properties'

$securePinA = Read-Host 'Stały PIN administratora ustawień' -AsSecureString
$securePinB = Read-Host 'Powtórz stały PIN administratora ustawień' -AsSecureString

function Convert-SecureStringToPlainText([Security.SecureString]$SecureValue) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

$pinA = Convert-SecureStringToPlainText $securePinA
$pinB = Convert-SecureStringToPlainText $securePinB

try {
    if ([string]::IsNullOrWhiteSpace($pinA)) {
        throw 'PIN administratora nie może być pusty.'
    }
    if ($pinA -notmatch '^[0-9]{6,}$') {
        throw 'PIN administratora musi mieć co najmniej 6 cyfr.'
    }
    if ($pinA -ne $pinB) {
        throw 'Podane PIN-y administratora nie są zgodne.'
    }

    $salt = 'wvc-iiyama-admin-settings-v1'
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes("${salt}:$pinA")
        $digest = $sha.ComputeHash($bytes)
        $adminHash = -join ($digest | ForEach-Object { $_.ToString('x2') })
    } finally {
        $sha.Dispose()
    }
} finally {
    $pinA = $null
    $pinB = $null
}

$serviceHash = ''
$serviceUids = ''
if (Test-Path $target) {
    foreach ($line in Get-Content $target) {
        if ($line -match '^servicePinSha256=(.*)$') {
            $serviceHash = $Matches[1].Trim()
        }
        if ($line -match '^serviceNfcUids=(.*)$') {
            $serviceUids = $Matches[1].Trim()
        }
    }
}

@(
    "servicePinSha256=$serviceHash"
    "serviceNfcUids=$serviceUids"
    "adminSettingsPinSha256=$adminHash"
) | Set-Content -Path $target -Encoding ascii

Write-Host "Stały PIN ustawień skonfigurowany lokalnie: $target"
Write-Host 'PIN nie jest zapisywany jawnie; do APK trafia wyłącznie salted SHA-256.'
Write-Host 'Nie ma możliwości zmiany tego PIN-u z poziomu HMI.'
