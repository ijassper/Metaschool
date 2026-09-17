#!/bin/bash
# Restart only this checkout's Gunicorn. Run git pull --ff-only separately.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$project_dir"
if [[ -x "$project_dir/.venv/bin/python" ]]; then
    python_bin="$project_dir/.venv/bin/python"
else
    python_bin="$(command -v python)"
fi
command -v flock >/dev/null || { echo 'flock가 없어 중복 재시작을 방지할 수 없습니다.'; exit 1; }
exec 9> .restart.lock
flock -n 9 || { echo '이미 재시작 중입니다.'; exit 1; }
export PROCTOR_FFMPEG="${PROCTOR_FFMPEG:-/web/tools/ffmpeg/ffmpeg-linux-amd64}"
"$python_bin" -m gunicorn --version
if [[ ! -x "$PROCTOR_FFMPEG" ]]; then
    echo "FFmpeg 실행파일을 확인하세요: $PROCTOR_FFMPEG"
    exit 1
fi
"$PROCTOR_FFMPEG" -hide_banner -encoders 2>/dev/null | grep -E ' libx264 ' >/dev/null || {
    echo 'FFmpeg libx264 인코더 확인에 실패했습니다.'; exit 1;
}
echo '1. 설치된 코드의 환경 및 DB 검사'
"$python_bin" -m pip install -r requirements.txt
"$python_bin" manage.py check
"$python_bin" manage.py migrate --noinput

app_masters() {
    "$python_bin" - "$project_dir" <<'PY'
import os
import sys
root = os.path.realpath(sys.argv[1])
targets = {}
for name in os.listdir('/proc'):
    if not name.isdigit():
        continue
    try:
        path = '/proc/' + name
        if os.stat(path).st_uid != os.getuid():
            continue
        with open(path + '/cmdline', 'rb') as handle:
            command = handle.read().replace(b'\0', b' ').decode(errors='replace')
        if 'gunicorn' not in command or 'config.wsgi:application' not in command:
            continue
        if os.path.realpath(path + '/cwd') != root:
            continue
        with open(path + '/stat') as handle:
            parent = int(handle.read().rsplit(')', 1)[1].split()[1])
        targets[int(name)] = parent
    except (OSError, ValueError):
        continue
for pid, parent in targets.items():
    if parent not in targets:
        print(pid)
PY
}

echo '2. 이 프로젝트의 기존 Gunicorn 정상 종료'
masters="$(app_masters)"
for pid in $masters; do
    kill -TERM "$pid"
done
for attempt in {1..30}; do
    remaining="$(app_masters)"
    [[ -z "$remaining" ]] && break
    sleep 1
done
if [[ -n "$(app_masters)" ]]; then
    echo '기존 서버가 아직 종료 중입니다. 요청 완료 후 다시 실행하세요. 강제 종료하지 않습니다.'
    exit 1
fi
if ss -ltn | awk '{print $4}' | grep -qE ':8080$'; then
    echo '8080 포트가 다른 프로세스에 의해 사용 중입니다. 새 서버를 실행하지 않습니다.'
    ss -ltnp | grep ':8080' || true
    exit 1
fi

echo '3. FFmpeg 설정을 포함하여 서버 시작'
nohup "$python_bin" -m gunicorn config.wsgi:application \
    --bind 0.0.0.0:8080 --workers 2 --timeout 200 \
    --pid "$project_dir/gunicorn.pid" --access-logfile - --error-logfile - \
    >> "$project_dir/gunicorn-runtime.log" 2>&1 9>&- < /dev/null &
new_pid=$!
ready=false
for attempt in {1..20}; do
    if ! kill -0 "$new_pid" 2>/dev/null; then break; fi
    if "$python_bin" - <<'PY'
import sys
import urllib.request
import urllib.error
request = urllib.request.Request('http://127.0.0.1:8080/robots.txt', headers={'Host': 'schoolingrid.com'})
try:
    with urllib.request.urlopen(request, timeout=2) as response:
        status = response.status
except urllib.error.HTTPError as error:
    status = error.code
except (OSError, urllib.error.URLError):
    sys.exit(1)
sys.exit(0 if 200 <= status < 400 or status == 404 else 1)
PY
    then ready=true; break; fi
    sleep 1
done
if [[ "$ready" != true ]]; then
    echo '서버 시작 확인 실패. 아래 로그를 확인하세요.'
    tail -n 50 "$project_dir/gunicorn-runtime.log"
    exit 1
fi
echo "서버 시작 확인 완료 (PID: $new_pid). 브라우저에서 사이트를 확인하세요."
echo '로그: tail -f /web/metaschool/gunicorn-runtime.log'
