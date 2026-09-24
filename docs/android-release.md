# Ingrid 학생 앱 release APK 배포

## 최초 한 번: 서명키 생성

PowerShell에서 다음 명령을 실행합니다.

```powershell
cd C:\GitHub\Metaschool\android-student
.\scripts\create-release-keystore.ps1
```

다음 두 파일을 암호화된 외장 저장소 등에 함께 백업해야 합니다.

- `android-student/signing/ingrid-student-release.jks`
- `android-student/keystore.properties`

두 파일은 Git에 포함되지 않습니다. 하나라도 잃으면 이미 설치된 앱을 같은 앱으로 업데이트할 수 없습니다.

## APK 생성

```powershell
cd C:\GitHub\Metaschool\android-student
.\scripts\build-release.ps1
```

성공하면 다음 파일이 생성됩니다.

```text
C:\GitHub\Metaschool\releases\ingrid-student.apk
```

## 운영 서버에 업로드

생성된 APK를 서버의 아래 경로에 업로드합니다.

```text
/web/metaschool/releases/ingrid-student.apk
```

파일이 존재하면 `/accounts/student-app/` 페이지의 QR 코드와 다운로드 버튼이 자동 활성화됩니다.

## 앱 업데이트

업데이트를 배포할 때는 `app/build.gradle`의 `versionCode`를 반드시 올리고, 사용자에게 보이는 `versionName`도 변경합니다. 최초 생성한 서명키를 계속 사용하여 새 APK를 만든 뒤 서버 파일을 교체합니다.
