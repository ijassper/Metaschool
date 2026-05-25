#!/bin/bash

echo "--- 🔄 Ingrid Server Sync & Restart ---"

# 1. GitHub 최신 코드 강제 동기화 (SFTP로 인한 충돌 원천 차단)
echo "1. GitHub로부터 최신 소스를 가져옵니다..."
git fetch --all
git reset --hard origin/main

# 2. 혹시 모를 라이브러리 및 DB 변경사항 반영
echo "2. 환경 및 데이터베이스 업데이트 중..."
pip install -r requirements.txt
python manage.py migrate --noinput

# 3. 기존 서버 프로세스 정리
echo "3. 기존 서버를 정리합니다..."
pkill -9 gunicorn || true
pkill -f "python3 manage.py runserver" || true
sleep 2

# 4. 서버 실행 (8080 포트 고정 및 로그 기록)
echo "4. 서버를 실행합니다 (Port: 8080)..."
nohup gunicorn config.wsgi:application --bind 0.0.0.0:8080 > nohup.out 2>&1 &

# 5. 결과 확인
echo "✅ 서버가 성공적으로 재시작되었습니다!"
echo "--- 📋 실시간 로그 모니터링 (종료: Ctrl+C) ---"

# 실시간 로그 출력 (이 상태로 유지됩니다)
tail -f nohup.out