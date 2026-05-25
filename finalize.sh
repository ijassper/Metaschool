#!/bin/bash

# ============================================================
# Ingrid Project - Final Deployment & Persistence Script
# 강사님의 숙면을 위한 마침표 스크립트 (GitHub Sync + Migrate + Start)
# ============================================================

echo "--- 🌙 Ingrid 마감 작업을 시작합니다 ---"

# 1. GitHub 최신 소스 강제 동기화 (SFTP 충돌 방지)
echo "1. GitHub에서 최신 레시피를 가져오는 중..."
git fetch --all
git reset --hard origin/main

# 2. 환경 및 데이터베이스 무결성 확보
echo "2. 라이브러리 및 DB 구조 업데이트 중..."
pip install -r requirements.txt --force-reinstall
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# 3. 기존 좀비 프로세스 완벽 정리
echo "3. 기존 서버를 정리하고 새 터를 잡습니다..."
pkill -9 gunicorn || true
sleep 2

# 4. 서버 영구 실행 (nohup + background)
# 포트는 가비아 최적화 포트인 8080을 사용합니다.
echo "4. 인그리드 엔진을 가동합니다 (무한 동력 모드)..."
nohup gunicorn config.wsgi:application --bind 0.0.0.0:8080 --access-logfile - --error-logfile - > nohup.out 2>&1 &

echo "--- ✅ 모든 작업이 완료되었습니다! ---"
echo "이제 이 터미널을 닫으셔도 서버는 24시간 멈추지 않습니다."
echo "브라우저에서 접속을 확인하고 기분 좋게 푹 쉬세요!"
echo "--- 📋 실시간 로그 (확인 후 Ctrl+C로 빠져나가세요) ---"

# 마지막으로 잘 도는지 눈으로 확인시켜드림
tail -f nohup.out