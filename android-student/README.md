# Ingrid Student Android

학생이 인그리드 평가에 응시하고, 감독 모드가 활성화된 활동에서 Android 화면 공유를 승인할 수 있도록 만드는 전용 앱입니다.

## 현재 단계

- Kotlin 기반 Android 앱 프로젝트
- 휴대전화와 태블릿 가로 화면 대응 기본 UI
- 로그인 및 감독 모드 안내 화면
- 앱 내부 WebView 학생 로그인과 세션 쿠키 유지
- 최소 Android 8(API 26), 대상 Android API 37

## 다음 단계

1. 로그인 이후 학생 대시보드와 답안 페이지 동작 검증
2. WebView 로그인 세션과 네이티브 업로드 요청의 Django CSRF 쿠키 연동
3. MediaProjection 화면 공유 권한 및 포그라운드 서비스 구현
4. 3초 간격 JPEG 생성 및 기존 감독 API 업로드
5. 공유 중단·앱 이탈·네트워크 오류 상태 처리

## 실행

Android Studio에서 `android-student` 폴더를 프로젝트로 열고 연결된 Android 기기에서 `app` 구성을 실행합니다.
