#!/bin/bash
# 1. 로컬(IDX) 변경사항 저장 및 푸시
git add .
git commit -m "Auto deploy from IDX: $(date +'%Y-%m-%d %H:%M:%S')"
git push origin main

echo "------------------------------------------"
echo "�� IDX -> GitHub 푸시 완료! 이제 가비아 서버를 업데이트합니다..."
echo "------------------------------------------"

# 2. 가비아 서버에 접속하여 풀(Pull) 및 재시작 명령 전송
# (비밀번호를 물어보면 아까 그 lee+yoon...을 입력하세요)
ssh -t guser@211.47.75.58 "cd metaschool && git fetch --all && git reset --hard origin/main && ./restart.sh"

echo "------------------------------------------"
echo "✅ 배포가 끝났습니다! schoolinggrid.com을 확인하세요."
echo "------------------------------------------"
