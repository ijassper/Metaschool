#!/bin/bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$project_dir"

if [[ -x "$project_dir/.venv/bin/python" ]]; then
    python_bin="$project_dir/.venv/bin/python"
else
    python_bin="$(command -v python)"
fi

command -v flock >/dev/null || { echo 'flock가 없어 감독 기록 자동 정리를 실행할 수 없습니다.'; exit 1; }
exec 9> "$project_dir/.proctor-cleanup.lock"
flock -n 9 || { echo '감독 기록 정리가 이미 실행 중이므로 이번 실행을 건너뜁니다.'; exit 0; }

"$python_bin" manage.py cleanup_proctor_snapshots "$@"
