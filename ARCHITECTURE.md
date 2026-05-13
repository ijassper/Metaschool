# 🏗 Ingrid Architecture & Design Philosophy
> 인그리드 프로젝트의 기술적 구조와 설계 원칙을 정리한 문서입니다.

---

## 1. 핵심 아키텍처: 통합 생성/수정 엔진
인그리드는 다양한 유형의 활동(교과 논술, 자율활동, 동아리 등)을 처리하기 위해 **'통합 생성/수정 엔진'** 구조를 채택하고 있습니다.

### 🧩 전략 (Strategy)
- **단일 엔트리포인트**: 모든 카테고리의 생성 및 수정은 `activities/views/manage_views.py` 내의 `unified_create` 및 `unified_update` 함수에서 처리됩니다.
- **동적 설정 (Dynamic Configuration)**: `get_form_config` 함수를 통해 카테고리별로 필요한 입력 필드, 라벨, 힌트 등을 JSON 형태로 가져와 템플릿에 주입합니다.
- **데이터 일관성**: 서로 다른 활동 유형이라도 동일한 `Activity` 모델을 공유하여 데이터 관리의 일관성을 유지합니다.

---

## 2. 데이터 흐름 및 브릿지 (Data Flow)
글로벌 UI 요소와 개별 폼 간의 원활한 데이터 전달을 위해 **JSON 데이터 브릿지** 방식을 사용합니다.

### 🌉 글로벌 모달 - 메인 폼 브릿지
- **상황**: `base.html`에 정의된 '학생 선택 모달'은 전역적으로 사용되지만, 선택된 데이터는 각 페이지의 폼에 전달되어야 합니다.
- **메커니즘**:
    1. 사용자가 글로벌 모달에서 대상 학생을 선택합니다.
    2. 자바스크립트가 선택된 학생 ID 목록을 JSON 문자열로 변환합니다.
    3. 메인 폼 내의 숨겨진 필드(`<input type="hidden" name="selected_students_json">`)에 이 값을 바인딩합니다.
    4. 폼 제출 시 서버(`manage_views.py`)에서 이 JSON을 파싱하여 `ManyToMany` 관계를 맺습니다.

---

## 3. 디자인 가이드라인 (Design System)
인그리드의 UI는 사용자의 몰입감을 높이고 현대적인 감각을 전달하기 위해 **글래스모피즘(Glassmorphism)** 테마를 따릅니다.

### 🎨 시각적 요소
- **테마**: `Backdrop-filter: blur(14px)`를 활용한 반투명 유리 질감.
- **코너**: 모든 카드(`card`), 입력창(`input`), 버튼은 **24px 이상의 둥근 모서리(Pill 스타일)**를 유지합니다.
- **컬러**: 
    - **Primary Gradient**: 핑크(`#FF80B5`)에서 보라(`#8E44AD`)로 이어지는 **135도 선형 그라데이션**.
    - **Background**: 연보라색 활성 배경(`#F3F0FF`) 및 밝은 그레이(`#F8F9FA`).

---

## 4. 앱 및 파일 구조 상세

### 📂 `activities` 앱: 기능 중심의 뷰 분리
코드의 비대화를 막기 위해 `views/` 디렉토리 내에 기능별로 파일을 분리하였습니다.
- **[manage_views.py](file:///c:/Users/pc/Documents/GitHub/Metaschool/activities/views/manage_views.py)**: 활동의 생성, 수정, 삭제, 상태 변경 등 관리자 기능.
- **[exam_views.py](file:///c:/Users/pc/Documents/GitHub/Metaschool/activities/views/exam_views.py)**: 학생들의 시험 응시, 임시 저장, 최종 제출 로직.
- **[result_views.py](file:///c:/Users/pc/Documents/GitHub/Metaschool/activities/views/result_views.py)**: 제출된 답안 목록 확인 및 개별 결과 조회.
- **[ai_views.py](file:///c:/Users/pc/Documents/GitHub/Metaschool/activities/views/ai_views.py)**: AI 엔진을 활용한 답안 분석 및 피드백 생성 로직.

### 📂 `accounts` 앱: 통합 대시보드
- 교사와 학생의 통합 대시보드를 관리하며, 학교 및 학생 데이터의 일괄 임포트 기능을 포함합니다.

---

## 5. 코딩 컨벤션 및 개발 원칙

### 📝 자바스크립트 및 데이터 바인딩
- **HTML 데이터 속성 활용**: JS에서 DOM 요소를 제어하거나 데이터를 참조할 때 `data-*` 속성(예: `data-student-id`)을 적극적으로 활용합니다.
- **관심사 분리**: 인라인 스크립트를 지양하고, 외부 JS 파일 또는 템플릿 하단의 `{% block extra_js %}`를 사용합니다.

### 📊 AI 분석 및 배치(Batch) 로직
- **중복 분석 방지**: 동일한 답안에 대해 여러 번 분석을 수행할 경우, `AnalysisResult` 모델의 `batch_id`를 통해 각 세션을 구분합니다.
- **열 분리 로직**: 결과 화면에서 여러 번의 분석 결과를 비교하거나 별도의 열로 출력할 때 'Batch' 개념을 기준으로 데이터를 필터링합니다.

---

이 문서는 인그리드 프로젝트의 정체성을 유지하기 위한 가이드라인입니다. 모든 신규 기능 개발 및 코드 수정 시 위 원칙을 준수해야 합니다.
