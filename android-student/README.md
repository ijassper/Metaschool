# Ingrid Student Android

학생이 인그리드 평가에 응시하고, 감독 모드가 활성화된 활동에서 Android 화면 공유를 승인할 수 있도록 만드는 전용 앱입니다.

## 현재 단계

- Kotlin 기반 Android 앱 프로젝트
- 휴대전화와 태블릿 가로 화면 대응 UI
- 앱 내부 WebView 학생 로그인, 대시보드, 답안 페이지와 세션 쿠키 유지
- MediaProjection 기반 3초 간격 감독 화면 전송
- 외부 앱 이탈 감지, 개인정보 보호 오버레이와 학생 식별 워터마크
- 화면 캡처 방지 및 녹화 중단 감지
- 네트워크 장애 재시도와 최대 20장 암호화 임시 저장
- 정상 전송, 임시 보관, 녹화 중단 상태 표시
- 서버 버전 API를 이용한 앱 업데이트 자동 확인
- 서명 APK와 교사용 QR 다운로드 페이지
- 최소 Android 8(API 26), 대상 Android API 37

## 출시 전 남은 작업

1. 학교 현장 20~30대 동시 접속 부하 시험
2. Galaxy Tab, 휴대전화, Android 주요 버전별 화면과 권한 흐름 시험
3. Wi-Fi 단절, 앱 강제 종료, 화면 공유 취소, 저장공간 부족 복구 시험
4. 설치·업데이트·서명키 백업 절차 최종 점검

감독 화면은 기본 30일 보관하며 `PROCTOR_RETENTION_DAYS` 환경변수로 변경할 수 있습니다.
자동 정리 작업을 등록하기 전 `python manage.py cleanup_proctor_snapshots --dry-run`으로 대상을 확인합니다.
서버 자동 정리는 `bash scripts/install-proctor-cleanup-cron.sh`로 하루 한 번 등록합니다.

## 출시 후 개선 후보

1. Play Store 비공개 배포 또는 학교 MDM 배포 전환
2. 자동화된 Android UI·네트워크 장애 테스트 확대
3. 교사 설정에 따른 전체 화면/앱 단독 공유 호환성 확대
4. 서버에서 앱 최소 지원 버전을 지정하는 강제 업데이트 정책

## 실행

Android Studio에서 `android-student` 폴더를 프로젝트로 열고 연결된 Android 기기에서 `app` 구성을 실행합니다.
