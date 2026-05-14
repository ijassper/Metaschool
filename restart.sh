#!/bin/bash
echo "1. 기존 서버를 정리합니다..."
pkill -f "python3 manage.py runserver" || true
sleep 2
echo "2. 서버를 백그라운드에서 실행합니다..."
nohup python3 manage.py runserver 0.0.0.0:8080 > nohup.out 2>&1 &
echo "3. 로그 출력을 시작합니다 (종료하려면 Ctrl+C)..."
sleep 2
tail -f nohup.out
