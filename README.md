# Ingrid (인그리드)

교사가 평가·활동을 만들고 학생의 답안, 교과 수업 노트, 출결 신고와 감독 기록을 관리하는 Django 웹 서비스입니다. 학생은 웹 또는 전용 Android 앱에서 참여합니다.

## 주요 기능

- **평가·활동:** 교과 논술형 평가와 자율·동아리·진로 등 학교 활동 생성, 대상 학생 지정, 답안 작성·자동 저장·제출, 제출 현황·점수·피드백·내보내기
- **응시 환경:** 개방형/폐쇄형 및 복사 허용 여부에 따른 제어. Android 앱에서는 화면 캡처 차단, 화면 고정 안내와 선택한 활동의 감독 화면 전송을 지원합니다. 학교 전체 기기를 중앙에서 관리하는 MDM은 포함하지 않습니다.
- **감독 기록:** 교사의 실시간 모니터링, 이벤트 확인, 기록 다시보기·검토·다운로드 및 보관 기간에 따른 이미지 정리
- **교과 수업 노트:** 교사의 노트 생성·학생 배정, 학생의 단원 구성·사진 업로드, 문서 보정·A4 PDF 보관, 텍스트 확인·수정. 로컬 OCR은 별도 실행 환경이 준비된 경우 사용합니다.
- **출결 신고:** 학년도별 폴더, 학생·교사의 신고서 작성, 교사의 제출 현황·미제출 학생 확인, 보호자 서명과 교사 확인 흐름
- **AI 보조:** 설정된 모델과 API 키에 따라 답안 분석·피드백 및 첨부자료 텍스트 추출을 실행합니다. 외부 API 호출은 설정과 사용량에 따라 비용이 발생할 수 있습니다.
- **학생 앱 배포:** 교사용 설치 페이지의 QR·APK 다운로드, 버전 확인과 최소 지원 버전 제한

## 기술 구성

| 영역 | 현재 구성 |
| --- | --- |
| 서버 | Python 3.8 호환, Django 4.2, Gunicorn, WhiteNoise |
| 화면 | Django 템플릿, Bootstrap, JavaScript |
| 데이터 | MySQL, 업로드 미디어 파일. 평가·활동 테이블은 이모지 저장을 위해 `utf8mb4` 사용 |
| 학생 앱 | Kotlin Android 앱, WebView, MediaProjection 감독 화면 전송 |
| 문서 처리 | Pillow, OpenCV, pypdf; 교과 수업 노트 OCR은 별도 로컬 워커 |
| AI | 관리자 설정에 따라 OpenAI·Gemini 등 지원 경로 사용 |

## 저장소 구조

```text
accounts/          계정·학교 관리, 대시보드, 시스템 설정, 앱 배포
activities/        평가·답안·감독·수업 노트·출결 신고
android-student/   학생용 Android 앱과 빌드 스크립트
config/            Django 설정 및 URL
templates/         서버 렌더링 화면
static/            정적 리소스
docs/              운영·배포 상세 문서
restart.sh         서버 검사·마이그레이션·Gunicorn 재시작
deploy.ps1         로컬 변경사항 커밋·푸시 보조 스크립트
```

## 개발 및 검증

`requirements.txt`로 Python 패키지를 설치합니다. 현재 `config/settings.py`에는 운영 MySQL 연결 설정이 들어 있으므로, **로컬에서 기본 설정으로 `migrate`나 데이터 변경 명령을 실행하지 마세요.** 개발·테스트용 DB 설정을 별도로 준비해야 합니다. 기존 README의 `.env`/`DATABASE_URL` 예시는 현재 코드에 구현된 설정 방식이 아니어서 제거했습니다.

DB 연결 없이 Django 검사를 수행하려면 다음 테스트 설정을 사용합니다. `config/test_settings.py`는 SQLite 메모리 DB와 마이그레이션 비활성화 설정이므로, MySQL 운영 마이그레이션의 실제 실행을 대신 검증하지는 않습니다.

```powershell
cd C:\GitHub\Metaschool
.\.venv\Scripts\python.exe manage.py check --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py test accounts activities --settings=config.test_settings --noinput
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
```

Android 앱은 Android Studio에서 `android-student` 폴더를 열어 개발합니다. 서명키·버전 관리·APK 업로드 절차는 [Android 릴리즈 안내](docs/android-release.md)를 참고하세요.

## 운영 배포

로컬에서 검증 후 변경 파일을 커밋·푸시합니다. `deploy.ps1`은 `git add .`로 **모든 변경 파일**을 포함하므로 실행 전 `git status`로 대상을 확인하세요. Android 소스만 바뀐 경우에는 웹 배포 외에 새 APK 빌드·업로드가 별도로 필요합니다.

```powershell
cd C:\GitHub\Metaschool
git status --short
.\deploy.ps1 "변경 내용"
```

운영 서버 `/web/metaschool`에서는 다음 순서로 실행합니다. `restart.sh`는 의존성·Django 검사와 마이그레이션을 **기존 Gunicorn 종료 전에** 실행합니다. DB 스키마가 바뀌는 배포는 사전 백업과 수업 외 시간대를 권장합니다.

```bash
cd /web/metaschool
git pull --ff-only origin main
bash restart.sh
```

배포가 실패하면 `gunicorn-runtime.log`와 터미널의 마이그레이션 오류를 확인하고, 무리하게 DB 기록을 `--fake` 처리하거나 저장소를 강제 초기화하지 마세요. 자세한 절차는 [서버 재시작 안내](docs/server-restart.md)에 있습니다.

감독 이미지는 기본 30일 보관합니다. 이 호스팅 환경에서는 `crontab`이 없을 수 있어 최고관리자 로그인 시 하루 한 번 백그라운드 정리를 시도합니다. 답안·제출 기록은 이 이미지 정리 대상이 아닙니다. [감독 기록 보관 안내](docs/proctor-retention.md)

## 관련 문서

- [학생 Android 앱](android-student/README.md)
- [Android APK 빌드·업로드](docs/android-release.md)
- [서버 배포·재시작](docs/server-restart.md)
- [감독 기록 다시보기](docs/proctor-replay.md)
- [감독 기록 보관·자동 정리](docs/proctor-retention.md)
- [출결 신고 원본 양식](docs/attendance/README.md)
