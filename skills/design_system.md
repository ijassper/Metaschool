# Ingrid Design System Skill
이 스킬은 인그리드 프론트엔드 작업 시 항상 참조해야 하는 규칙입니다.

## 1. Architectural Patterns
- **Unified Engine**: 모든 활동 생성/수정은 `activities/views/manage_views.py`의 `unified_create`/`unified_update`를 통할 것. `get_form_config`로 설정 주입.
- **JSON Data Bridge**: 글로벌 모달과 폼 데이터 통신은 JSON 문자열 변환 후 hidden input 바인딩 방식을 준수할 것.
- **State Logic**: 학생 상태는 반드시 4단계[미응시 / 응시 중 / 백지 제출 / 제출 완료] 로직을 엄수하여 제어할 것.

## 2. Design System (Must Follow)
- **Visual**: `Backdrop-filter: blur(14px)` 글래스모피즘 테마.
- **Components**: 모든 카드, 입력창, 버튼은 `border-radius: 24px` (Pill 스타일) 고정.
- **Colors**: 
  - Primary Gradient: `#FF80B5` → `#8E44AD` (135도)
  - Background: `#F3F0FF` (연보라 활성), `#F8F9FA` (기본)

## 3. Directory & File Conventions
- **activities/**: 비즈니스 로직 중심.
  - `manage_views.py`: 관리자용 생성/수정/상태 관리.
  - `exam_views.py`: 응시/임시저장/최종제출.
  - `result_views.py`: 결과 조회.
  - `ai_views.py`: 분석/피드백 로직.
- **templates/**: 공통 컴포넌트 사용 원칙.
  - 모달, 그리드 등은 `components/` 하위 컴포넌트 활용.

## 4. Coding & AI Rules
- **Data Binding**: JS 제어 시 `data-*` 속성을 사용할 것.
- **AI/Batch Logic**: 
  - `AnalysisResult` 모델의 `batch_id`와 `work_name` 필드를 사용하여 중복 분석 방지 및 피벗 테이블 생성할 것.
- **Persistence**: 로직 수정 시 `localStorage`나 서버 `context`를 통해 입력값 유지(Persistence) 기능을 보존할 것.
- **Forbidden**: `__pycache__`, `*.pyc`, `.venv`, `.env`는 절대 커밋하지 말 것.

## 5. Dynamic Card Theming Rule (Mandatory)
모든 동적 카드(학생 그룹, 학급 섹션, 결과 카드 등)를 렌더링할 때, 다음 디자인 규칙을 준수하십시오:

- **Pastel Color Palette**: 카드의 배경색은 반드시 아래 7개 클래스 중 하나를 랜덤하게 할당해야 합니다.
  - `.pastel-purple`, `.pastel-blue`, `.pastel-green`, `.pastel-yellow`, `.pastel-orange`, `.pastel-red`, `.pastel-pink`
- **Implementation Strategy**:
  - CSS에 정의된 클래스들을 사용하십시오.
  - JavaScript를 사용하여 컴포넌트가 로드되거나 모달이 열릴 때, 해당 컨테이너(`div`)에 위 클래스 중 하나를 무작위로 주입(classList.add)해야 합니다.
  - 기존 클래스(필요시)는 유지하되, 색상 클래스는 충돌하지 않도록 먼저 제거(`remove`) 후 추가(`add`)하는 로직을 사용하십시오.
- **Visual Consistency**: 모든 카드는 `rounded-24px`와 `border`를 기본값으로 하여, 배경색과 테두리색이 정의된 팔레트와 일치해야 합니다.