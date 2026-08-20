param(
    [Parameter(Mandatory = $true)]
    [string]$NfcUid
)

$ErrorActionPreference = 'Stop'

$normalizedUid = ($NfcUid -replace '[\s:\-]', '').ToUpperInvariant()
if ($normalizedUid -notmatch '^[0-9A-F]+$') {
    throw 'NFC UID must contain only hexadecimal digits.'
}

$securePin = Read-Host 'PIN serwisowy' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePin)
try {
    $pin = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($pin)) {
    throw 'PIN serwisowy nie może być pusty.'
}

$salt = 'wvc-iiyama-service-exit-v1'
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $bytes = [Text.Encoding]::UTF8.GetBytes("${salt}:$pin")
    $digest = $sha.ComputeHash($bytes)
    $hash = -join ($digest | ForEach-Object { $_.ToString('x2') })
} finally {
    $sha.Dispose()
    $pin = $null
}

$target = Join-Path $PSScriptRoot '..\service-access.properties'
$adminHash = ''
if (Test-Path $target) {
    foreach ($line in Get-Content $target) {
        if ($line -match '^adminSettingsPinSha256=(.*)$') {
            $adminHash = $Matches[1].Trim()
        }
    }
}

$lines = @(
    "servicePinSha256=$hash"
    "serviceNfcUids=$normalizedUid"
)
if (-not [string]::IsNullOrWhiteSpace($adminHash)) {
    $lines += "adminSettingsPinSha256=$adminHash"
}
$lines | Set-Content -Path $target -Encoding ascii

Write-Host "Service access configured locally: $target"
Write-Host "NFC UID: $normalizedUid"
Write-Host 'PIN zapisany wyłącznie jako salted SHA-256.'
if (-not [string]::IsNullOrWhiteSpace($adminHash)) {
    Write-Host 'Stały PIN ustawień zachowany.'
}
