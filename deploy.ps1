# Ingrid 배포 스크립트 (Local -> GitHub)
# 사용법: .\deploy.ps1 "커밋 메시지"

param (
    [Parameter(Mandatory=$false)]
    [string]$Message = "Update Ingrid templates and components"
)

Write-Host "🚀 Ingrid 배포 프로세스를 시작합니다..." -ForegroundColor Cyan

# 1. 모든 변경사항 스테이징
Write-Host "📦 변경사항 스테이징 중..." -ForegroundColor Yellow
git add .

# 2. 커밋
Write-Host "📝 커밋 중: $Message" -ForegroundColor Yellow
git commit -m "$Message"

# 3. 푸시
Write-Host "📤 GitHub로 푸시 중..." -ForegroundColor Yellow
git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ GitHub 푸시 성공!" -ForegroundColor Green
    Write-Host "💡 이제 서버 터미널에서 다음 명령어를 실행하세요:" -ForegroundColor White
    Write-Host "   git pull && ./restart.sh" -ForegroundColor Magenta
} else {
    Write-Host "❌ 배포 중 오류가 발생했습니다." -ForegroundColor Red
}
