# 가비아 서버 배포 / 재시작

서버 `/web/metaschool`에서 다음을 실행한다.

```bash
git pull --ff-only origin main
bash restart.sh
```

새 restart.sh는 코드 동기화를 하지 않는다. `git reset --hard`와 전체 Python
프로세스 종료를 제거했다. git pull 충돌 시 강제로 덮어쓰지 말고 먼저 변경사항을 확인한다.
기존 `python -m gunicorn`도 찾아서 정상 종료한다. 현재 사용자 소유이며 작업 디렉터리가
이 checkout이고 config.wsgi:application을 실행하는 Gunicorn 마스터만 대상으로 한다.
30초 내 종료되지 않으면 강제 종료하지 않고 중단한다. 기존 요청이 끝난 후 다시 시도한다.
다른 프로세스가 8080을 사용하면 실행을 거부한다.

매 재시작마다 FFmpeg 경로의 기본값 `/web/tools/ffmpeg/ffmpeg-linux-amd64`를 적용한다.
다른 위치를 사용하면 PROCTOR_FFMPEG 환경변수로 지정한다.
가상환경 `.venv/bin/python`이 있으면 사용하고, 없으면 현재 PATH의 python을 사용한다.
requirements 설치, Django check, migrate가 실패하면 기존 서버 종료 전에 중단한다.
마이그레이션은 DB 상태를 변경하므로 필요 시 사전 백업하고 응시하지 않는 시간에 배포한다.

신규 Gunicorn은 worker 2개, timeout 200초를 사용한다.
PID 파일은 gunicorn.pid, 로그는 gunicorn-runtime.log다. 로그는 덮어쓰지 않는다.
로컬 HTTP 응답까지 확인한 뒤 성공을 출력하며 무한 tail 없이 종료한다.
robots.txt 404는 이 시작 확인 요청에서 정상 결과다.
외부 도메인/프록시 연결과 MP4 다운로드는 브라우저로 별도 확인한다.

```bash
tail -n 80 gunicorn-runtime.log
ss -ltnp | grep ':8080'
```

컨테이너 재부팅 시 자동 기동 설정은 별도이다. 이 스크립트는 수동 배포/재시작용이며,
가비아 supervisord 설정은 현재 확인·수정하지 않았다.
