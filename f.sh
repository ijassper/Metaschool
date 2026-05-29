#!/bin/bash
# 파일명: f.sh (가장 짧게!)

echo "🚀 Ingrid 마감 시작"

# 1. 동기화 (SFTP 충돌 방지)
git fetch --all && git reset --hard origin/main

# 2. 필요한 것만 설치/반영 (속도 대폭 향상)
pip install -r requirements.txt  # --force-reinstall 제거
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# 3. 서버 재시작
pkill -9 gunicorn || true
sleep 1
nohup gunicorn config.wsgi:application --bind 0.0.0.0:8080 --daemon

echo "✅ 완료! 로그를 보려면: tail -f nohup.out"
echo "나가려면 바로 exit를 입력하세요."