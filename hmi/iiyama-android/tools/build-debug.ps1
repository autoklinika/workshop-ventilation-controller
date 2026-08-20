$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Gradle = 'C:\Android\gradle\gradle-9.4.1\bin\gradle.bat'
$Sdk = "$env:LOCALAPPDATA\Android\Sdk"
$LocalProperties = Join-Path $ProjectRoot 'local.properties'

if (-not (Test-Path $Gradle)) {
    throw "Gradle not found: $Gradle"
}

if (-not (Test-Path $Sdk)) {
    throw "Android SDK not found: $Sdk"
}

if (-not (Test-Path $LocalProperties)) {
    $SdkGradlePath = $Sdk -replace '\\','/'
    "sdk.dir=$SdkGradlePath" | Set-Content $LocalProperties -Encoding ASCII
    Write-Host "Created local.properties for SDK: $Sdk"
}

Push-Location $ProjectRoot
try {
    & $Gradle assembleDebug
    if ($LASTEXITCODE -ne 0) {
        throw "Gradle build failed with exit code $LASTEXITCODE"
    }

    $Apk = Join-Path $ProjectRoot 'app\build\outputs\apk\debug\app-debug.apk'
    if (-not (Test-Path $Apk)) {
        throw "Build completed but APK was not found: $Apk"
    }

    Write-Host "HMI debug APK ready: $Apk"
}
finally {
    Pop-Location
}
