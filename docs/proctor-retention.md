# 감독 화면 기록 보관 및 자동 정리

감독 스냅숏은 서버 수신 시각을 기준으로 기본 30일 보관합니다. 답안, 제출 기록, 감독 이벤트, 활동 정보는 이 정리 작업의 대상이 아닙니다.

## 삭제 대상 확인

```bash
python manage.py cleanup_proctor_snapshots --dry-run
```

## 자동 정리 등록

프로젝트 디렉터리에서 다음 명령을 한 번 실행합니다.

```bash
bash scripts/install-proctor-cleanup-cron.sh
```

매일 오전 3시 17분에 실행되며 같은 작업의 중복 실행은 `flock`으로 차단합니다. 기존 사용자 cron 항목은 보존하고 `# ingrid-proctor-cleanup` 표시가 붙은 항목만 교체합니다.

보관 기간을 변경해 등록하려면 다음과 같이 실행합니다.

```bash
PROCTOR_RETENTION_DAYS=60 bash scripts/install-proctor-cleanup-cron.sh
```

## 다음 날 확인

```bash
crontab -l | grep ingrid-proctor-cleanup
tail -n 50 proctor-cleanup.log
```

`crontab`이 없거나 cron 데몬이 실행되지 않는 호스팅에서는 가비아 관리 콘솔의 스케줄러 또는 고객센터를 통해 같은 실행 명령을 하루 한 번 등록해야 합니다.
