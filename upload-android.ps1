param(
    [string]$ServerHost = "211.47.75.58",
    [string]$ServerUser = "jacknov",
    [string]$RemotePath = "/web/metaschool/releases/ingrid-student.apk",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$apkPath = Join-Path $projectRoot "releases\ingrid-student.apk"

if (-not (Test-Path -LiteralPath $apkPath -PathType Leaf)) {
    throw "Release APK not found: $apkPath`nRun android-student\scripts\build-release.ps1 first."
}

$apk = Get-Item -LiteralPath $apkPath
$hash = (Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash
$sizeMb = [Math]::Round($apk.Length / 1MB, 2)

Write-Host ""
Write-Host "Ingrid Student APK Upload" -ForegroundColor Magenta
Write-Host "File: $apkPath"
Write-Host "Size: $sizeMb MB"
Write-Host "SHA-256: $hash"
Write-Host "Target: ${ServerUser}@${ServerHost}:$RemotePath"
Write-Host ""

$scp = Get-Command scp.exe -ErrorAction SilentlyContinue
if (-not $scp) {
    throw "scp.exe was not found. Install the Windows OpenSSH Client optional feature."
}

if ($DryRun) {
    Write-Host "DryRun: no file was uploaded." -ForegroundColor Yellow
    exit 0
}

& $scp.Source `
    -o "HostKeyAlgorithms=+ssh-rsa" `
    -o "PubkeyAcceptedKeyTypes=+ssh-rsa" `
    $apkPath `
    "${ServerUser}@${ServerHost}:$RemotePath"

if ($LASTEXITCODE -ne 0) {
    throw "APK upload failed. Review the SSH error above."
}

Write-Host ""
Write-Host "APK upload completed." -ForegroundColor Green
Write-Host "If server code also changed, run git pull and restart.sh separately on the server."
