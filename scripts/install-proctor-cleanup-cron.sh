#!/bin/bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
runner="$project_dir/scripts/run-proctor-cleanup.sh"
log_file="$project_dir/proctor-cleanup.log"
marker='# ingrid-proctor-cleanup'
retention_days="${PROCTOR_RETENTION_DAYS:-30}"

[[ "$retention_days" =~ ^[0-9]+$ ]] && (( retention_days >= 1 )) || {
    echo 'PROCTOR_RETENTION_DAYS는 1 이상의 정수여야 합니다.'
    exit 1
}
command -v crontab >/dev/null || {
    echo '이 서버에는 crontab 명령이 없습니다. 가비아 관리 콘솔의 스케줄러 지원 여부를 확인하세요.'
    exit 1
}
command -v flock >/dev/null || { echo 'flock 명령이 필요합니다.'; exit 1; }

echo '1. 삭제 대상 모의 확인'
/bin/bash "$runner" --days "$retention_days" --dry-run

cron_line="17 3 * * * /bin/bash $runner --days $retention_days >> $log_file 2>&1 $marker"
temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
{
    crontab -l 2>/dev/null | grep -Fv "$marker" || true
    echo "$cron_line"
} > "$temporary"
crontab "$temporary"

echo '2. 매일 오전 3시 17분 자동 정리 등록 완료'
crontab -l | grep -F "$marker"
if ! pgrep -x crond >/dev/null 2>&1 && ! pgrep -x cron >/dev/null 2>&1; then
    echo '경고: 현재 계정에서 cron 데몬을 확인하지 못했습니다.'
    echo '컨테이너 외부에서 실행될 수도 있지만, 내일 로그가 생성되는지 반드시 확인하세요.'
fi
echo "실행 로그: $log_file"
