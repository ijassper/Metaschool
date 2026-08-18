# 생성/수정/삭제/상태변경 (unified_create, delete 등)

import calendar
import json
import logging
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.timezone import make_aware
from django.http import JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_POST

# [핵심] 같은 폴더(views) 내의 main_views에서 공통 함수 가져오기
from .main_views import get_accessible_student_ids, get_form_config, get_student_tree

# [핵심] 상위 폴더(..)의 models.py에서 모델들 가져오기
from ..models import Activity, Question, Answer, ActivityFile

# [중요] 교사 권한 데코레이터 가져오기 (accounts 앱에서)
from accounts.decorators import teacher_required
from accounts.models import Persona


ACTIVITY_ITEM_TITLE_MAX_LENGTH = 2000


def get_activity_item_title_error(post_data):
    """DB 저장 전에 답안지 항목 제목 길이를 검증하여 사용자용 오류를 반환합니다."""
    for index in range(1, 4):
        field_name = f'q{index}_title'
        value = str(post_data.get(field_name, '') or '').strip()
        if len(value) > ACTIVITY_ITEM_TITLE_MAX_LENGTH:
            return (
                f"학생 답안지 구성의 '항목 {index} 제목' 글자 수가 너무 많습니다. "
                f"{ACTIVITY_ITEM_TITLE_MAX_LENGTH:,}자 이하로 입력해주세요."
            )
    return ''

logger = logging.getLogger(__name__)

PERSONA_TONES = ["친절한", "신뢰있는", "친구같은", "격려하는", "간결한", "전문적인"]


def _persona_form_values(request):
    valid_contexts = {value for value, _ in Persona.CategoryContext.choices}
    valid_task_types = {value for value, _ in Persona.TaskType.choices}
    category_context = request.POST.get("category_context", "").strip()
    task_type = request.POST.get("task_type", "").strip()
    return {
        "name": request.POST.get("name", "").strip(),
        "description": request.POST.get("description", "").strip(),
        "system_prompt": request.POST.get("system_prompt", "").strip(),
        "tone_default": request.POST.get("tone_default", "친절한").strip() or "친절한",
        "category_context": category_context if category_context in valid_contexts else "",
        "task_type": task_type if task_type in valid_task_types else "",
    }


@login_required
@teacher_required
def persona_list(request):
    personas = Persona.objects.filter(Q(creator__isnull=True) | Q(creator=request.user)).select_related("creator")
    return render(request, "activities/persona_list.html", {
        "system_personas": personas.filter(creator__isnull=True),
        "personal_personas": personas.filter(creator=request.user),
    })


@login_required
@teacher_required
def persona_create(request):
    form_data = {}
    if request.method == "POST":
        form_data = _persona_form_values(request)
        if not form_data["name"] or not form_data["system_prompt"]:
            messages.error(request, "페르소나 이름과 시스템 프롬프트는 필수입니다.")
        else:
            Persona.objects.create(creator=request.user, **form_data)
            messages.success(request, f"'{form_data['name']}' 페르소나를 등록했습니다.")
            return redirect("persona_list")
    return render(request, "activities/persona_form.html", {
        "form_data": form_data,
        "tone_options": PERSONA_TONES,
        "category_options": Persona.CategoryContext.choices,
        "task_type_options": Persona.TaskType.choices,
        "action": "등록",
    })


@login_required
@teacher_required
def persona_update(request, persona_id):
    persona = get_object_or_404(Persona, id=persona_id, creator=request.user)
    form_data = None
    if request.method == "POST":
        form_data = _persona_form_values(request)
        if not form_data["name"] or not form_data["system_prompt"]:
            messages.error(request, "페르소나 이름과 시스템 프롬프트는 필수입니다.")
        else:
            for field, value in form_data.items():
                setattr(persona, field, value)
            persona.save()
            messages.success(request, f"'{persona.name}' 페르소나를 수정했습니다.")
            return redirect("persona_list")
    return render(request, "activities/persona_form.html", {
        "persona": persona,
        "form_data": form_data,
        "tone_options": PERSONA_TONES,
        "category_options": Persona.CategoryContext.choices,
        "task_type_options": Persona.TaskType.choices,
        "action": "수정",
    })


@require_POST
@login_required
@teacher_required
def persona_delete(request, persona_id):
    persona = get_object_or_404(Persona, id=persona_id, creator=request.user)
    name = persona.name
    persona.delete()
    messages.success(request, f"'{name}' 페르소나를 삭제했습니다.")
    return redirect("persona_list")

def normalize_typing_duration(value):
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return None
    return min(max(duration, 1), 600)

def get_allowed_choice_values(choices):
    return {value for value, _label in choices}

def apply_typing_settings_from_post(activity, post_data):
    typing_types = get_allowed_choice_values(Activity.TYPING_TYPE_CHOICES)
    typing_positions = get_allowed_choice_values(Activity.TYPING_POSITION_CHOICES)
    typing_levels = get_allowed_choice_values(Activity.TYPING_LEVEL_CHOICES)

    activity.typing_type = post_data.get('typing_type') if post_data.get('typing_type') in typing_types else 'SHORT_MISSION'
    activity.typing_position = post_data.get('typing_position') if post_data.get('typing_position') in typing_positions else 'BOTH'
    activity.typing_level = post_data.get('typing_level') if post_data.get('typing_level') in typing_levels else 'BEGINNER_0'
    activity.duration = normalize_typing_duration(post_data.get('duration'))
    activity.show_keyboard = post_data.get('show_keyboard') == 'on'
    activity.target_data = post_data.get('target_data', '').strip()

def sync_status_on_deadline_extension(activity, old_deadline, new_deadline):
    """
    제출 기한이 연장되었을 때, 기존 답안 중 아직 답안 제출하지 않은(submitted_at is null)
    학생들의 activity_log에 기한 연장 메시지를 추가하여 상태가 복구되었음을 기록합니다.
    """
    now = timezone.now()
    if old_deadline and new_deadline:
        if new_deadline > old_deadline and new_deadline > now:
            answers = Answer.objects.filter(question__activity=activity, submitted_at__isnull=True)
            local_now = timezone.localtime(now)
            for answer in answers:
                timestamp = local_now.strftime('%Y-%m-%d %H:%M:%S')
                log_msg = f"[{timestamp}] 선생님의 기한 연장으로 재응시 가능 상태로 복구됨\n"
                answer.activity_log = (answer.activity_log or "") + log_msg
                answer.save(update_fields=['activity_log'])

# 통합 생성 페이지 (카테고리와 소메뉴에 따라 유동적으로 필드 라벨과 저장 방식 결정)
@login_required
@teacher_required
def unified_create(request):
    # 1. URL 파라미터에서 정보 가져오기
    cat_code = request.GET.get('category', 'ESSAY')
    sub_menu = request.GET.get('sub', '과목별 수행평가')
    
    # 메뉴별 설정 가져오기
    config = get_form_config(sub_menu)
    category_name = dict(Activity.CATEGORY_CHOICES).get(cat_code, "평가/활동")
    source_answer = None
    source_answer_id = request.GET.get('source_answer')
    followup_type = request.GET.get('followup_type', 'grading')
    if source_answer_id and source_answer_id.isdigit():
        source_answer = get_object_or_404(
            Answer.objects.select_related('student', 'question__activity'),
            id=source_answer_id,
            question__activity__teacher=request.user,
        )

    if request.method == 'POST':
        # [내부 함수] 날짜 파싱
        def parse_dt(dt_str):
            if not dt_str: return None
            try:
                # 24시간 형식 파싱 (예: 2026. 05. 17. 14:00)
                naive_dt = datetime.strptime(dt_str, "%Y. %m. %d. %H:%M")
                return make_aware(naive_dt)
            except ValueError:
                try:
                    # 기존 12시간 형식(오전/오후) 호환성 유지
                    clean_dt = dt_str.replace('오후', 'PM').replace('오전', 'AM')
                    naive_dt = datetime.strptime(clean_dt, "%Y. %m. %d. %p %I:%M")
                    return make_aware(naive_dt)
                except: return None

        # [수정: 섹션 2 평가 문항 처리] 
        # 루프 방식 대신 HTML의 name="question"에서 직접 가져와 유실을 방지합니다.
        main_question = request.POST.get('question', '').strip()
        
        # [신규] 유효성 검사 (항목 1 제목 필수)
        q1_title = request.POST.get('q1_title', '').strip()
        if not q1_title:
            messages.error(request, "학생 답안지 구성의 '항목 1 제목'은 필수 입력 사항입니다.")
            return render(request, 'activities/unified_form.html', {
                'cat_code': cat_code, 
                'sub_menu': sub_menu, 
                'config': config,
                'student_tree': get_student_tree(request.user),
                'action': '생성',
                'form_data': request.POST
            })

        item_title_error = get_activity_item_title_error(request.POST)
        if item_title_error:
            messages.error(request, item_title_error)
            return render(request, 'activities/unified_form.html', {
                'cat_code': cat_code,
                'sub_menu': sub_menu,
                'config': config,
                'student_tree': get_student_tree(request.user),
                'action': '생성',
                'form_data': request.POST,
                'source_answer': source_answer,
            })
        
        # 만약 루프 방식(q1, q2...)을 병행해야 한다면 아래 로직을 사용하지만, 
        # 현재 설계도대로라면 위 코드가 가장 확실합니다.
        if not main_question:
            for area in config.get('textareas', []):
                val = request.POST.get(area['name'], '').strip()
                if val:
                    main_question += f"[{area['label']}]\n{val}\n\n"

        # 추가 정보 처리 (기존 로직 유지)
        extra_info = []
        for inp in config.get('inputs', []):
            if inp['name'] not in ['section', 'title', 'activity_date']:
                val = request.POST.get(inp['name'])
                if val: extra_info.append(f"{inp['label']}: {val}")
        extra_str = f" ({', '.join(extra_info)})" if extra_info else ""

        # [데이터 브릿지] 글로벌 모달에서 온 JSON 데이터 수신 및 파싱
        json_data = request.POST.get('selected_students_json', '')
        target_ids = []
        
        print(f"[DEBUG] 폼 데이터 전체 키 목록: {list(request.POST.keys())}")
        print(f"[DEBUG] selected_students_json 원본 데이터: '{json_data}'")
        
        if json_data:
            try:
                import json
                target_ids = json.loads(json_data)
                print(f"[브릿지] JSON 파싱 성공 - 학생 ID 목록: {target_ids}")
                print(f"[브릿지] 학생 수: {len(target_ids)}명")
            except json.JSONDecodeError as e:
                print(f"[오류] JSON 파싱 실패: {json_data}")
                print(f"[오류] 파싱 에러 상세: {str(e)}")
                target_ids = []
        else:
            print(f"[정보] selected_students_json 필드가 비어있음")
        
        # 기존 방식도 지원 (호환성)
        if not target_ids:
            target_ids = request.POST.getlist('target_students')
            print(f"[호환성] 기존 방식 학생 ID 목록: {target_ids}")
            print(f"[호환성] 기존 방식 학생 수: {len(target_ids)}명")
        
        # 최종 수신된 학생 ID 목록 확인
        print(f"[최종 결과] 수신된 학생 ID 목록: {target_ids}")
        print(f"[최종 결과] 최종 학생 수: {len(target_ids)}명")
        
        try:
            # --- [Activity 객체 생성] ---
            activity = Activity.objects.create(
                teacher=request.user,
                category=cat_code,
                sub_category=sub_menu,
                
                # [섹션 1: 기본 정보]
                section=request.POST.get('section', sub_menu),
                title=request.POST.get('title', '제목 없음') + extra_str,
                exam_mode=request.POST.get('exam_mode', 'CLOSED_LOCK'),
                allow_edit_after_submission=request.POST.get('allow_edit_after_submission') == 'True',
                deadline=parse_dt(request.POST.get('deadline')), # 섹션 1 기한
                
                # [섹션 2: 세부 평가 내용]
                # [비활성화] 수업 일시(activity_date)는 UI/로직에서 제외합니다.
                # DB 필드는 보존하되 신규 생성 시에는 null로 둡니다.
                activity_date=None,
                question=main_question,  
                reference_material=request.POST.get('reference_material', ''),
                conditions=request.POST.get('conditions', ''),
                char_limit=int(request.POST.get('char_limit', 0)) if request.POST.get('char_limit') else 0,
                attachment=None, # 다중 파일 모델(ActivityFile) 사용
                
                # [섹션 3: 기타 중요 내용 (AI 분석용)]
                achievement_standard=request.POST.get('achievement_standard', ''),
                evaluation_elements=request.POST.get('evaluation_elements', ''),
                
                # [섹션 4: 학생 답안지 구성 (문항 제목)]
                q1_title=request.POST.get('q1_title', config.get('default_q', [''])[0]),
                q2_title=request.POST.get('q2_title', config.get('default_q', ['',''])[1]),
                q3_title=request.POST.get('q3_title', config.get('default_q', ['','',''])[2]),
            )

            if config.get('typing_fields'):
                apply_typing_settings_from_post(activity, request.POST)
                activity.save(update_fields=[
                    'typing_type',
                    'typing_position',
                    'typing_level',
                    'duration',
                    'show_keyboard',
                    'target_data',
                ])

            print(f"[생성] Activity 객체 생성 완료 - ID: {activity.id}")

            # --- [즉시 학생 매칭 수술] ---
            # activity.save() 직후에 selected_students_json 값을 가져와서 즉시 강제 연결
            json_data = request.POST.get('selected_students_json', '')
            student_ids = []
            
            if json_data:
                try:
                    import json
                    student_ids = json.loads(json_data)
                    print(f"[수술] JSON에서 즉시 파싱된 학생 ID 목록: {student_ids}")
                    print(f"[수술] 학생 수: {len(student_ids)}명")
                except json.JSONDecodeError as e:
                    print(f"[오류] JSON 파싱 실패: {json_data}")
                    print(f"[오류] 파싱 에러 상세: {str(e)}")
                    student_ids = []
            else:
                print(f"[정보] selected_students_json 필드가 비어있음")
            
            # [즉시 강제 연결] 새로 만들어진 번호에 학생들을 즉시 강제 연결
            if student_ids:
                activity.target_students.set(get_accessible_student_ids(request.user, student_ids))
                print(f"[수술 성공] 즉시 학생 연결 완료: {len(student_ids)}명")
                # 연결된 학생 목록 확인
                connected_students = list(activity.target_students.values_list('id', flat=True))
                print(f"[수술 확인] DB에 연결된 학생 ID 목록: {connected_students}")
                print(f"[수술 확인] DB에 연결된 학생 수: {len(connected_students)}명")
            else:
                print(f"[수술 경고] 학생 데이터 없음 - 연결 생략")

            # --- [다중 파일 저장] ---
            files = request.FILES.getlist('attachments')
            for f in files:
                ActivityFile.objects.create(activity=activity, file=f)

            # --- [후속 처리] ---
            # 1. Question 객체 생성 (Answer 모델과의 연결을 위해 필수)
            from ..models import Question
            Question.objects.create(
                activity=activity, 
                content=main_question, # Activity와 동일한 내용 복사
                conditions=activity.conditions
            )

            messages.success(request, f"'{sub_menu}' 시트가 성공적으로 생성되었습니다.")
            return redirect(f'/activities/list/?category={cat_code}&sub={sub_menu}')

        except Exception as e:
            logger.error(f"생성 에러: {str(e)}")
            print(f"DEBUG: Form errors: {e}")
            messages.error(request, f"저장 중 오류가 발생했습니다: {str(e)}")
            # 입력 데이터 복구: request.POST의 값들을 다시 폼에 채워주기
            return render(request, 'activities/unified_form.html', {
                'cat_code': cat_code, 
                'sub_menu': sub_menu, 
                'config': config,
                'student_tree': get_student_tree(request.user),
                'action': '생성',
                'form_data': request.POST  # 실패한 데이터를 다시 전달
            })

    # 7. GET 요청 시
    form_data = None
    if source_answer:
        source_activity = source_answer.question.activity
        student = source_answer.student
        followup_presets = {
            'grading': {
                'title': f"{student.name} 학생 답안 채점 및 분석",
                'question': (
                    "이전 답안을 평가 기준에 따라 검토하고, 잘된 점과 보완할 점을 "
                    "구체적인 근거와 함께 정리하세요."
                ),
            },
            'feedback': {
                'title': f"{student.name} 학생 피드백 활동",
                'question': (
                    "이전 답안에 대한 피드백을 확인하고, 피드백에서 새롭게 알게 된 점과 "
                    "다음 활동에서 실천할 내용을 작성하세요."
                ),
            },
            'rewrite': {
                'title': f"{student.name} 학생 고쳐쓰기 활동",
                'question': (
                    "이전 답안의 강점은 유지하고 보완할 부분을 수정하여 더 나은 글로 "
                    "다시 작성하세요."
                ),
            },
            'relay': {
                'title': f"{student.name} 학생 릴레이쓰기 활동",
                'question': (
                    "이전 답안의 마지막 생각을 출발점으로 삼아 내용을 자연스럽게 이어 쓰고, "
                    "새로운 관점이나 사건을 더하세요."
                ),
            },
        }
        followup_preset = followup_presets.get(followup_type, followup_presets['grading'])
        form_data = {
            'section': source_activity.section,
            'title': followup_preset['title'],
            'exam_mode': source_activity.exam_mode,
            'question': followup_preset['question'],
            'reference_material': (
                f"[이전 활동]\n{source_activity.title}\n\n"
                f"[{student.name} 학생 답안]\n{source_answer.display_content}"
            ),
        }

    return render(request, 'activities/unified_form.html', {
        'cat_code': cat_code, 
        'sub_menu': sub_menu, 
        'config': config,
        'student_tree': get_student_tree(request.user),
        'action': '생성',
        'form_data': form_data,
        'source_answer': source_answer,
        'current_targets': [source_answer.student_id] if source_answer else [],
    })

# 통합 수정 페이지 (카테고리와 소메뉴에 따라 유동적으로 필드 라벨과 저장 방식 결정)
@login_required
@teacher_required
def unified_update(request, activity_id):
    # 1. 기존 데이터 불러오기
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    
    # 2. 설정 정보 가져오기
    sub_menu = activity.sub_category if activity.sub_category else "과목별 수행평가"
    config = get_form_config(sub_menu)
    category_name = dict(Activity.CATEGORY_CHOICES).get(activity.category, "평가/활동")

    if request.method == 'POST':
        # [내부 함수] 날짜 파싱
        def parse_dt(dt_str):
            if not dt_str: return None
            try:
                # 24시간 형식 파싱 (예: 2026. 05. 17. 14:00)
                naive_dt = datetime.strptime(dt_str, "%Y. %m. %d. %H:%M")
                return make_aware(naive_dt)
            except ValueError:
                try:
                    # 기존 12시간 형식(오전/오후) 호환성 유지
                    clean_dt = dt_str.replace('오후', 'PM').replace('오전', 'AM')
                    naive_dt = datetime.strptime(clean_dt, "%Y. %m. %d. %p %I:%M")
                    return make_aware(naive_dt)
                except: return None

        item_title_error = get_activity_item_title_error(request.POST)
        if item_title_error:
            messages.error(request, item_title_error)
            return render(request, 'activities/unified_form.html', {
                'activity': activity,
                'cat_code': activity.category,
                'sub_menu': sub_menu,
                'config': config,
                'category_name': category_name,
                'current_targets': list(activity.target_students.values_list('id', flat=True)),
                'student_tree': get_student_tree(request.user),
                'action': '수정',
                'form_data': request.POST,
            })

        # ------------------------------------------------
        # 3. [핵심 수정] 데이터 업데이트 (실제 DB 반영)
        # ------------------------------------------------
        
        # [섹션 1: 기본 정보]
        activity.section = request.POST.get('section', activity.section)
        activity.title = request.POST.get('title', activity.title)
        activity.exam_mode = request.POST.get('exam_mode', 'CLOSED_LOCK')
        activity.allow_edit_after_submission = request.POST.get('allow_edit_after_submission') == 'True'
        
        # [섹션 2: 세부 평가 내용] - 루프 없이 직접 매핑하여 유실 차단
        # HTML의 <textarea name="question"> 값을 직접 가져옴
        new_question = request.POST.get('question', '').strip()
        if new_question:
            activity.question = new_question
        
        activity.reference_material = request.POST.get('reference_material', '')
        activity.conditions = request.POST.get('conditions', '')
        
        # 작성 분량 (숫자 변환 예외처리)
        try:
            activity.char_limit = int(request.POST.get('char_limit', 0))
        except (ValueError, TypeError):
            activity.char_limit = 0

        # [섹션 3: 기타 중요 내용 (AI 분석용)]
        activity.achievement_standard = request.POST.get('achievement_standard', '')
        activity.evaluation_elements = request.POST.get('evaluation_elements', '')

        # [섹션 4: 학생 답안지 구성 제목] - 교사가 설정한 제목들
        new_q1_title = request.POST.get('q1_title', '').strip()
        if not new_q1_title:
            messages.error(request, "학생 답안지 구성의 '항목 1 제목'은 필수 입력 사항입니다.")
            return render(request, 'activities/unified_form.html', {
                'activity': activity,
                'cat_code': activity.category,
                'sub_menu': sub_menu,
                'config': config,
                'category_name': category_name,
                'current_targets': list(activity.target_students.values_list('id', flat=True)),
                'student_tree': get_student_tree(request.user),
                'action': '수정'
            })
        
        activity.q1_title = new_q1_title
        activity.q2_title = request.POST.get('q2_title', activity.q2_title)
        activity.q3_title = request.POST.get('q3_title', activity.q3_title)

        if config.get('typing_fields'):
            apply_typing_settings_from_post(activity, request.POST)
        
        old_deadline = activity.deadline
        # [비활성화] 수업 일시(activity_date)는 UI/로직에서 제외합니다.
        # 기존 데이터 보존을 위해 수정 시 POST 값이 들어와도 변경하지 않습니다.
        if request.POST.get('deadline'):
            activity.deadline = parse_dt(request.POST.get('deadline'))

        # 기한 연장 동기화 로직
        sync_status_on_deadline_extension(activity, old_deadline, activity.deadline)

        # ------------------------------------------------
        # 4. 다중 파일 관리 로직
        # ------------------------------------------------
        # (1) 삭제 체크된 파일 처리
        delete_file_ids = request.POST.getlist('delete_files')
        if delete_file_ids:
            ActivityFile.objects.filter(id__in=delete_file_ids, activity=activity).delete()

        # (2) 새로 추가된 파일 저장
        new_files = request.FILES.getlist('attachments')
        for f in new_files:
            ActivityFile.objects.create(activity=activity, file=f)

        # 5. 최종 저장
        activity.save()

        # 6. 학생 매칭 업데이트 (데이터 브릿지 사용)
        json_data = request.POST.get('selected_students_json', '')
        target_ids = []
        
        if json_data:
            try:
                import json
                target_ids = json.loads(json_data)
                print(f"[브릿지-수정] JSON에서 파싱된 학생 ID 목록: {target_ids}")
            except json.JSONDecodeError:
                print(f"[오류-수정] JSON 파싱 실패: {json_data}")
                target_ids = []
        
        # 기존 방식도 지원 (호환성)
        if not target_ids:
            target_ids = request.POST.getlist('target_students')
            print(f"[호환성-수정] 기존 방식 학생 ID 목록: {target_ids}")
        
        if target_ids:
            activity.target_students.set(get_accessible_student_ids(request.user, target_ids))
            print(f"[성공-수정] 대상 학생 업데이트 완료: {len(target_ids)}명")
        else:
            print(f"[경고-수정] 대상 학생이 선택되지 않음")

        messages.success(request, f"'{activity.title}' 수정이 완료되었습니다.")
        return redirect(f'/activities/list/?category={activity.category}&sub={sub_menu}')

    # 7. GET 요청 시: 기존 데이터 렌더링 준비
    current_targets = list(activity.target_students.values_list('id', flat=True))

    return render(request, 'activities/unified_form.html', {
        'activity': activity,
        'cat_code': activity.category,
        'sub_menu': sub_menu,
        'config': config,
        'category_name': category_name,
        'current_targets': current_targets,
        'student_tree': get_student_tree(request.user),
        'action': '수정'
    })

# 통합 삭제 (단일 삭제)
@login_required
@teacher_required
def unified_delete(request, activity_id):
    # 1. 삭제할 활동 데이터 불러오기
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)

    # 2. [핵심] 삭제 전 리다이렉트에 필요한 카테고리 정보를 미리 변수에 담아둡니다.
    cat_code = activity.category
    sub_menu = activity.sub_category

    # 3. 실제 삭제 수행
    activity.delete()

    # 4. 안내 메시지 처리
    messages.success(request, "평가활동이 성공적으로 삭제되었습니다.")

    # 5. [중요] 삭제 전 보관했던 파라미터를 붙여서 '원래 보던 목록'으로 보내줍니다.
    # 이렇게 해야 동아리 삭제 후 다시 동아리 목록이 나옵니다. (학급 및 메뉴 등 모든 쿼리 파라미터 보존)
    from urllib.parse import urlencode
    
    params = {}
    for key in ['category', 'sub', 'class_id', 'q']:
        val = request.GET.get(key)
        if val:
            params[key] = val
            
    targets = request.GET.getlist('target')
    if targets:
        params['target'] = targets
        
    if 'category' not in params:
        params['category'] = cat_code
    if 'sub' not in params and sub_menu:
        params['sub'] = sub_menu
        
    query_string = urlencode(params, doseq=True)
    return redirect(f'/activities/list/?{query_string}')

# 평가 상태 토글 (시작 <-> 마감)
@login_required
@teacher_required
def toggle_activity_status(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)

    def add_one_month(dt):
        year = dt.year + (1 if dt.month == 12 else 0)
        month = 1 if dt.month == 12 else dt.month + 1
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)

    now = timezone.now()
    old_deadline = activity.deadline
    is_deadline_passed = bool(activity.deadline and now > activity.deadline)
    deadline_extended = False

    if activity.is_active:
        activity.is_active = False
        status_msg = "평가가 [마감]되었습니다."
        update_fields = ['is_active']
    else:
        activity.is_active = True
        activity.allow_edit_after_submission = True
        if is_deadline_passed:
            activity.deadline = add_one_month(now)
            deadline_extended = True
            sync_status_on_deadline_extension(activity, old_deadline, activity.deadline)
            status_msg = "평가가 [시작]되었고 제출 기한이 1개월 연장되었습니다."
            update_fields = ['is_active', 'allow_edit_after_submission', 'deadline']
        else:
            status_msg = "평가가 [시작]되었습니다."
            update_fields = ['is_active', 'allow_edit_after_submission']

    activity.save(update_fields=update_fields)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'activity_id': activity.id,
            'is_active': activity.is_active,
            'is_attainable': activity.is_attainable,
            'is_effectively_active': activity.is_effectively_active,
            'allow_edit_after_submission': activity.allow_edit_after_submission,
            'status_code': activity.status_code,
            'status_text': activity.status_text,
            'deadline': activity.deadline.isoformat() if activity.deadline else '',
            'deadline_display': timezone.localtime(activity.deadline).strftime('%Y-%m-%d %H:%M') if activity.deadline else '기한 없음',
            'deadline_extended': deadline_extended,
            'message': status_msg,
        })

    messages.success(request, status_msg)
    fallback_url = f'/activities/list/?category={activity.category}&sub={activity.sub_category}'
    return redirect(request.META.get('HTTP_REFERER', fallback_url))

# 창의적체험활동 생성
@login_required
def creative_create(request):
    # URL에서 소메뉴 정보를 가져옴 (예: /create/?sub=범교과교육)
    sub_menu = request.GET.get('sub', '일반')

    if request.method == 'POST':
        
        # 1. 폼 데이터 먼저 모두 받아오기 (변수에 담기)
        post_sub_menu = request.POST.get('sub_category')
        title = request.POST.get('title')
        section = request.POST.get('section')
        question = request.POST.get('question')
        conditions = request.POST.get('conditions', '')
        reference_material = request.POST.get('reference_material', '')
        deadline_str = request.POST.get('deadline')
        
        # 작성 분량 숫자 변환
        char_limit_raw = request.POST.get('char_limit', '').strip()
        char_limit = int(char_limit_raw) if char_limit_raw else 0
        
        # 응시 환경 유형
        exam_mode = request.POST.get('exam_mode', 'CLOSED_LOCK')
        
        # 파일 업로드
        attachment = request.FILES.get('attachment')

        # 날짜 처리
        deadline = None
        if deadline_str:
            try:
                temp_str = deadline_str.replace('오후', 'PM').replace('오전', 'AM')
                deadline = datetime.strptime(temp_str, "%Y. %m. %d. %p %I:%M")
            except:
                deadline = None

        # 2. [중요] 여기서 'activity' 변수를 생성합니다 (모든 필드를 한 번에 넣기)
        activity = Activity.objects.create(
            teacher=request.user,
            category='CREATIVE',
            sub_category = post_sub_menu, # 폼에서 넘어온 소메뉴 저장
            subject_name=request.user.subject.name if hasattr(request.user, 'subject') and request.user.subject else "공통",
            title=title,
            section=section,
            question=question,
            conditions=conditions,
            reference_material=reference_material,
            deadline=deadline,
            attachment=attachment,
            char_limit=char_limit,
            exam_mode=exam_mode,
        )

        # 3. 자율활동용 문항(Question) 자동 생성 (답안 제출 에러 방지)
        from ..models import Question
        Question.objects.create(
            activity=activity,
            content=question,
            conditions=conditions,
        )

        # 4. 학생 등록
        target_ids = request.POST.getlist('target_students')
        if target_ids:
            activity.target_students.set(get_accessible_student_ids(request.user, target_ids))
            
        return redirect('creative_list')

    # GET 요청 시
    student_tree = get_student_tree(request.user)
    return render(request, 'activities/creative_form.html', {
        'sub_menu': sub_menu,
        'student_tree': student_tree,
        'action': '생성'
    })

# 창의적체험활동 수정
@login_required
def creative_update(request, pk):
    # 1. 수정할 데이터를 DB에서 가져오기 (이 줄이 반드시 먼저 있어야 합니다)
    activity = get_object_or_404(Activity, pk=pk, teacher=request.user)
    
    if request.method == 'POST':
        # 2. POST 요청일 때: 사용자가 입력한 값으로 DB 업데이트
        activity.section = request.POST.get('section') # 활동명 (스크린샷에 빠져있던 부분)
        activity.title = request.POST.get('title')     # 주제
        activity.question = request.POST.get('question')
        activity.conditions = request.POST.get('conditions')
        activity.reference_material = request.POST.get('reference_material')
        char_limit_raw = request.POST.get('char_limit', '').strip()
        if not char_limit_raw:  # 빈칸('')이거나 데이터가 없으면
            char_limit = 0
        else:
            try:
                char_limit = int(char_limit_raw)
            except ValueError:
                char_limit = 0

        # 이후 객체 저장 시 이 char_limit 값을 사용합니다.
        activity.char_limit = char_limit
        
        # 만약 예전 파일(attachment)이 남아있다면, 새 테이블로 옮겨주고 기존 필드는 비우기
        if activity.attachment:
            ActivityFile.objects.create(activity=activity, file=activity.attachment)
            activity.attachment = None # 이전 필드 비우기

        # 파일 업로드 처리 (새 파일이 있을 때만 교체)
        if request.FILES.get('attachment'):
            activity.attachment = request.FILES.get('attachment')
            
        old_deadline = activity.deadline
        # 날짜 처리
        deadline_str = request.POST.get('deadline')
        if deadline_str:
            try:
                # 오후/오전 한글 대응
                temp_str = deadline_str.replace('오후', 'PM').replace('오전', 'AM')
                activity.deadline = datetime.strptime(temp_str, "%Y. %m. %d. %p %I:%M")
            except:
                pass

        # 기한 연장 동기화 로직
        sync_status_on_deadline_extension(activity, old_deadline, activity.deadline)

        # 시험 모드 설정
        activity.exam_mode = request.POST.get('exam_mode', 'CLOSED_LOCK')
            
        # 데이터 저장
        activity.save()

        question_obj, created = Question.objects.get_or_create(activity=activity)
        question_obj.content = activity.question
        question_obj.conditions = activity.conditions
        question_obj.reference_material = activity.reference_material
        question_obj.save()

        # 학생 재설정
        target_ids = request.POST.getlist('target_students')
        if target_ids:
            activity.target_students.set(get_accessible_student_ids(request.user, target_ids))
            
        # 수정 완료 후 상세 페이지로 이동
        return redirect('creative_detail', pk=activity.pk)

    # 3. GET 요청일 때: 수정 페이지 화면을 보여주기
    # 학생 트리와 현재 선택된 학생 목록을 준비합니다.
    context = {
        'activity': activity,
        'student_tree': get_student_tree(request.user),
        'current_targets': list(activity.target_students.values_list('id', flat=True)), # 현재 선택된 학생 ID들
        'action': '수정'
    }
    # 반드시 context를 포함하여 render를 호출해야 화면에 값이 나옵니다.
    return render(request, 'activities/creative_form.html', context)

# 창의적체험활동 삭제
@login_required
def creative_delete(request, pk):
    activity = get_object_or_404(Activity, pk=pk, teacher=request.user)
    if request.method == 'POST':
        activity.delete()
        return redirect('creative_list')
    return redirect('creative_detail', pk=pk)
