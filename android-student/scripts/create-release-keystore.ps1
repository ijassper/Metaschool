param(
    [string]$KeytoolPath = "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$signingDirectory = Join-Path $projectRoot "signing"
$keystorePath = Join-Path $signingDirectory "ingrid-student-release.jks"
$propertiesPath = Join-Path $projectRoot "keystore.properties"

if (-not (Test-Path -LiteralPath $KeytoolPath)) {
    throw "keytool을 찾을 수 없습니다: $KeytoolPath"
}

if ((Test-Path -LiteralPath $keystorePath) -or (Test-Path -LiteralPath $propertiesPath)) {
    throw "기존 서명키 또는 keystore.properties가 있습니다. 업데이트 호환성을 위해 자동으로 덮어쓰지 않습니다."
}

New-Item -ItemType Directory -Path $signingDirectory -Force | Out-Null
$passwordBytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($passwordBytes)
$password = [Convert]::ToBase64String($passwordBytes).Replace("+", "A").Replace("/", "B").Replace("=", "")

& $KeytoolPath `
    -genkeypair `
    -v `
    -keystore $keystorePath `
    -storepass $password `
    -keypass $password `
    -alias "ingrid-student" `
    -keyalg RSA `
    -keysize 4096 `
    -validity 10000 `
    -dname "CN=Ingrid Student, OU=Ingrid, O=SchoolingGrid, L=Seoul, ST=Seoul, C=KR"

if ($LASTEXITCODE -ne 0) {
    throw "서명키 생성에 실패했습니다."
}

$properties = @(
    "storeFile=signing/ingrid-student-release.jks"
    "storePassword=$password"
    "keyAlias=ingrid-student"
    "keyPassword=$password"
) -join [Environment]::NewLine

[System.IO.File]::WriteAllText($propertiesPath, $properties + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

Write-Host "서명키 생성 완료"
Write-Host "백업 필수: $keystorePath"
Write-Host "백업 필수: $propertiesPath"
