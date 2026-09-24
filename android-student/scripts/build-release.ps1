$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$javaHome = "C:\Program Files\Android\Android Studio\jbr"

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "keystore.properties"))) {
    throw "keystore.properties가 없습니다. 먼저 scripts/create-release-keystore.ps1을 실행하세요."
}

$env:JAVA_HOME = $javaHome
Push-Location $projectRoot
try {
    & ".\gradlew.bat" ":app:stageReleaseApk"
    if ($LASTEXITCODE -ne 0) {
        throw "release APK 빌드에 실패했습니다."
    }
} finally {
    Pop-Location
}

$stagedApk = Join-Path (Split-Path -Parent $projectRoot) "releases\ingrid-student.apk"
Write-Host "배포용 APK 생성 완료: $stagedApk"
