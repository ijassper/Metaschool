# 목록 조회 (unified_list, creative_list 등)

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.models import Student
from ..models import Activity  # [중요] 한 단계 위 폴더의 models에서 가져옴

# [중요] 교사 권한 데코레이터 가져오기 (accounts 앱에서)
from accounts.decorators import teacher_required


# [공통 함수] 학생 선택용 트리 데이터 생성 (학년-반-학생 구조)
def get_student_tree(teacher):
    students = Student.objects.filter(teacher=teacher).order_by('grade', 'class_no', 'number')
    
    tree = {}
    for s in students:
        if s.grade not in tree: tree[s.grade] = {}
        if s.class_no not in tree[s.grade]: tree[s.grade][s.class_no] = []
        
        # 학생 정보 (ID, 번호, 이름)
        tree[s.grade][s.class_no].append({
            'id': s.id,
            'number': s.number,
            'name': s.name
        })
    
    # 정렬된 리스트 형태로 변환 (템플릿용)
    tree_list = []
    for g in sorted(tree.keys()):
        classes = []
        for c in sorted(tree[g].keys()):
            classes.append({
                'class_no': c,
                'students': tree[g][c]
            })
        tree_list.append({'grade': g, 'classes': classes})
        
    return tree_list

# [공통 함수] 소메뉴별 설정값 관리 (카테고리와 소메뉴에 따라 유동적으로 필드 라벨과 저장 방식 결정)
def get_form_config(sub_menu):
    """
    Ingrid 시스템의 모든 소메뉴별 4대 섹션 라벨 및 필드 구성 데이터
    구조: basic(1섹션), detail(2섹션), ai_info(3섹션), textareas(2섹션 상세), default_q(4섹션)
    """
    configs = {
        # ==========================================
        # 1. 교과 논술형 평가
        # ==========================================
        '과목별 수행평가': {
            'basic': {'section': '과목명', 'title': '평가 영역'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'}, # 라벨 정의
            'textareas': [{'name': 'question', 'label': '평가 문항'}], # 가변 필드
            'ai_info': ['achievement_standard', 'evaluation_elements'],
            'default_q': ['문항 1', '', '']
        },

        # ==========================================
        # 2. 교과 수업활동 평가
        # ==========================================
        '발표활동 보고서': {
            'basic': {'section': '과목명', 'title': '발표 주제'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'},
            'textareas': [{'name': 'question', 'label': '평가 문항'}], # 설계도 준수: 단일 문항
            'ai_info': [], # 기타 중요 내용: 평가 대상(기본) 외 없음
            'default_q': ['발표 내용', '발표 성과', '발표 소감']
        },
        '모둠활동 보고서': {
            'basic': {'section': '과목명', 'title': '수업 주제'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'},
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [],
            'default_q': ['협동 과정', '나의 역할', '모둠 성과']
        },
        '창작활동 보고서': {
            'basic': {'section': '과목명', 'title': '창작 주제'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'},
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': ['achievement_standard'], # 설계도 준수: 성취 기준 포함
            'default_q': ['창작 기획', '제작 과정', '최종 완성본 설명']
        },
        '실기활동 보고서': {
            'basic': {'section': '과목명', 'title': '실기 주제'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'},
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': ['achievement_standard'], # 설계도 준수: 성취 기준 포함
            'default_q': ['수행 기술', '연습 과정', '최종 성과']
        },

        # ==========================================
        # 3. 교내 행사활동
        # ==========================================
        '행사활동 기록/분석': {
            'basic': {
                'section': '연관 과목/부서', # 설계도: 과목명/부서 반영
                'title': '행사 주제'        # 설계도: 행사 주제 반영
            },
            'detail': {
                'date': '행사 일시',         # 설계도: 행사 일시 반영
                'content': '평가 문항'       # 설계도: 평가 문항으로 통일
            },
            # 섹션 2: 가변 문항 (설계도에 따라 단일 문항으로 통합)
            'textareas': [
                {'name': 'question', 'label': '평가 문항'}
            ],
            # 섹션 3: 기타 중요 내용 (평가 대상은 공통이므로 리스트 비움)
            'ai_info': [],
            # 섹션 4: 학생 답안지 기본 항목 제목
            'default_q': ['참여 동기', '활동 내용', '배우고 느낀 점']
        },

        # ==========================================
        # 4. 자율활동
        # ==========================================
        '범교과교육': {
            'basic': {'section': '범교과교육명', 'title': '세부 주제'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'},
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [], # 설계도 준수: 평가 대상 외 없음
            'default_q': ['핵심 가치 이해', '실천 사례', '나의 다짐']
        },
        '학교주도활동': {
            'basic': {'section': '학교주도활동명', 'title': '세부 주제'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'},
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [],
            'default_q': ['활동 과정', '성과 분석', '향후 계획']
        },
        '현장체험학습': {
            'basic': {'section': '현장체험학습명', 'title': '세부 주제'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'},
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [],
            'default_q': ['사전 준비', '현장 활동', '사후 소감']
        },
        '학생자치회활동': {
            'basic': {'section': '학생자치회 부서', 'title': '세부 주제'},
            'detail': {'date': '수업 일시', 'content': '평가 문항'},
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [],
            'default_q': ['회의 안건', '나의 의견', '최종 결정 사항']
        },

        # ==========================================
        # 5. 동아리활동
        # ==========================================
        '동아리활동 일지': {
            'basic': {'section': '동아리명', 'title': '세부 주제'},
            'detail': {
                'date': '수업 일시',         # 설계도: 수업 일시
                'content': '평가 문항'
            },
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [],
            'default_q': ['활동 내용', '배운 점', '향후 계획']
        },
        '동아리활동 보고서': {
            'basic': {'section': '동아리명', 'title': '세부 주제'},
            'detail': {
                'date': '수업 학기',         # 설계도: 수업 학기
                'content': '평가 문항'
            },
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [],
            'default_q': ['학기 활동 요약', '주요 성과', '성장 포인트']
        },

        # ==========================================
        # 6. 진로활동
        # ==========================================
        '진로수업 일지': {
            'basic': {'section': '진로활동명', 'title': '세부 주제'},
            'detail': {
                'date': '수업 일시',         # 설계도: 수업 일시
                'content': '평가 문항'
            },
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [],
            'default_q': ['관심 분야 탐구', '주요 활동', '진로 연결성']
        },
        '진로수업 학기말 보고서': {
            'basic': {'section': '진로활동명', 'title': '세부 주제'},
            'detail': {
                'date': '수업 학기',         # 설계도: 수업 학기
                'content': '평가 문항'
            },
            'textareas': [{'name': 'question', 'label': '평가 문항'}],
            'ai_info': [],
            'default_q': ['학기 성장 기록', '진로 변화 과정', '향후 진로 계획']
        },
    }

    # 매칭되는 소메뉴가 없을 때 사용할 기본 설정
    default_config = {
        'basic': {'section': '활동명', 'title': '주제'},
        'detail': {'date': '일시', 'content': '내용'},
        'inputs': [
            {'name': 'section', 'label': '활동명', 'type': 'text'},
            {'name': 'title', 'label': '주제', 'type': 'text'}
        ],
        'textareas': [{'name': 'q1', 'label': '활동 상세 내용'}],
        'ai_info': [],
        'default_q': ['항목 1', '항목 2', '항목 3']
    }

    return configs.get(sub_menu, default_config)

# 계정 찾기 (임시)
def find_account(request):
    return render(request, 'registration/find_account.html')

# 통합 목록 페이지 (카테고리 선택 가능)
@login_required
def unified_list(request):
    # 1. URL 파라미터에서 카테고리 코드를 가져옴 (예: ?category=CLUB)
    cat_code = request.GET.get('category', 'ESSAY')
    sub_name = request.GET.get('sub', '과목별 수행평가') # 기본값 설정
    
    # 현재 메뉴에 맞는 라벨 설정 가져오기
    config = get_form_config(sub_name)

    activities = Activity.objects.filter(teacher=request.user, category=cat_code)

    # 소메뉴(sub) 정보가 있다면 한 번 더 필터링
    if sub_name:
        activities = activities.filter(sub_category=sub_name)

    # 2. 카테고리 한글명 매핑 (딕셔너리 활용)
    category_map = dict(Activity.CATEGORY_CHOICES)

    # 제목 결정: 소메뉴가 있으면 소메뉴명을, 없으면 대분류명을 제목으로 사용
    display_name = sub_name if sub_name else category_map.get(cat_code, "평가/활동")
    
    return render(request, 'activities/unified_list.html', {
        'activities': activities.order_by('-created_at'),
        'category_name': display_name,
        'cat_code': cat_code,
        'sub_menu': sub_name,    # 템플릿의 버튼 링크 생성용
        'config': config  # 템플릿에서 머리글로 사용하기 위해 전달
    })

# 창의적체험활동 목록
@login_required
def creative_list(request):
    # 로그인한 선생님이 작성한 '창의적체험활동' 카테고리만 필터링
    activities = Activity.objects.filter(
        teacher=request.user, 
        category='CREATIVE' # 창체 카테고리만 필터링
    ).order_by('-created_at')
    
    return render(request, 'activities/creative_list.html', {
        'activities': activities
    })

# 통합 상세 페이지 (모든 평가/활동 공용)
@login_required
@teacher_required
def activity_detail(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    
    # URL에서 받은 sub_menu 정보를 바탕으로 config 가져오기 (사이드바 활성화 유지)
    sub_menu = request.GET.get('sub', activity.sub_category)
    config = get_form_config(sub_menu) 
    
    questions = activity.questions.all()
    
    return render(request, 'activities/activity_detail.html', {
        'activity': activity, 
        'questions': questions, 
        'config': config
    })

# 자율활동 전용 상세 페이지 (레거시 지원용)
@login_required
def creative_detail(request, pk):
    activity = get_object_or_404(Activity, pk=pk, teacher=request.user)
    return render(request, 'activities/creative_detail.html', {'activity': activity})