# 🏫 Ingrid (인그리드)
> **교사용 지능형 평가 관리 시스템**

인그리드(Ingrid)는 AI 기술을 활용하여 교사의 학생 답안 분석 업무를 자동화하고, 학생의 논술형 답변 및 수업 활동 기록을 효율적으로 관리할 수 있도록 돕는 스마트 에듀테크 플랫폼입니다.

---

## 🌟 프로젝트 핵심 가치
- **업무 경감**: 수작업으로 진행되던 학생 답안 분석 및 피드백 작성을 AI가 보조하여 교사의 행정 시간을 단축합니다.
- **데이터 기반 지도**: 누적된 활동 데이터를 통해 학생 개개인의 성장 과정을 정교하게 추적합니다.
- **통합 관리**: 교과 논술부터 창의적 체험활동(자율, 동아리, 진로)까지 모든 학교 활동을 하나의 플랫폼에서 관리합니다.

---

## 🛠 기술 스택 (Tech Stack)
- **Backend**: Python 3.8 / Django 4.1
- **Frontend**: Bootstrap 5.3 / Vanilla JS (ES6+)
- **Database**: MySQL
- **AI Engine**: Google Gemini API (Analysis & Feedback)
- **Server**: Gunicorn / Nginx

---

## 📂 프로젝트 구조
```text
Metaschool/
├── accounts/          # 사용자 관리 및 대시보드 (Student, Teacher 모델)
├── activities/        # 활동/평가 관리 핵심 앱
│   ├── views/         # 기능별 뷰 분리 (manage, exam, result, ai)
│   └── models.py      # Activity, Answer, AnalysisResult 등 핵심 모델
├── config/            # Django 프로젝트 설정
├── static/            # 정적 파일 (CSS, JS, Images)
├── templates/         # HTML 템플릿 (Glassmorphism 테마 적용)
└── manage.py
```

---

## 🚀 시작하기

### 1. 환경 설정
`.env` 파일을 생성하고 필요한 환경 변수를 설정합니다.
```env
DEBUG=True
SECRET_KEY=your_secret_key
DATABASE_URL=mysql://user:password@localhost:3306/ingrid_db
GEMINI_API_KEY=your_api_key
```

### 2. 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. 데이터베이스 마이그레이션
```bash
python manage.py migrate
```

### 4. 서버 실행
```bash
python manage.py runserver
```

---

## 📘 상세 문서
- [설계 철학 및 아키텍처 (ARCHITECTURE.md)](./ARCHITECTURE.md)
- [디자인 시스템 가이드라인](./ARCHITECTURE.md#3-디자인-가이드라인)

---

© 2024 Ingrid Project. All rights reserved.
