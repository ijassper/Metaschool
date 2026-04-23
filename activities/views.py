from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.decorators import teacher_required
from django.contrib import messages
from django.utils import timezone # 날짜 표시용
from django.utils.timezone import make_aware    # 시간대 인식 datetime 변환
from datetime import datetime   # 날짜 비교용
from django.db.models import Q  # 복합 필터링
import json
import requests
import random
import openai
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 모델과 폼 가져오기
from .models import Activity, ActivityFile, Question, Answer
from .forms import ActivityForm, QuestionForm, AnswerForm
from accounts.models import Student, SystemConfig, PromptTemplate, PromptCategory, PromptLengthOption
import logging
logger = logging.getLogger(__name__)

# 공통 함수: 서브 메뉴에 따른 폼 설정값 반환 (계정 찾기)
def find_account(request):
    return render(request, 'registration/find_account.html')

# 1. 학생 대시보드 (응시 가능한 평가/활동 목록)
@login_required
def student_dashboard(request):
    # 1. 학생 객체 찾기 (이메일로 학생 찾기)
    student_profile = Student.objects.filter(email=request.user.email).first()
    
    if not student_profile:
        # 이메일로 못 찾으면 연결된 프로필(OneToOne)로 찾기 시도
        student_profile = getattr(request.user, 'student', None)

    # 1, 2단계를 모두 거쳤는데도 없다면? (에러 방지를 위해 빈 결과 반환)
    if not student_profile:
        return render(request, 'activities/student_dashboard.html', {'student': None})

    # 2. 이 학생에게 할당된 모든 활동 가져오기 (상태 필터 일단 제거하여 데이터 확인)
    all_activities = Activity.objects.filter(
        target_students=student_profile,
        is_active=True  # 선생님이 시작 버튼을 누른 것만 노출
    ).order_by('-created_at')

    # 3. [데이터 매핑] 각 활동에 학생의 답안 정보를 미리 붙여줌 (템플릿 에러 방지)
    for act in all_activities:
        ans = act.get_student_answer(student_profile)
        print(f"DEBUG: 활동[{act.title}] - 답변존재여부: {bool(ans)}")
        act.my_answer = ans

    # (디버깅용 출력: 가비아 터미널에서 확인 가능)
    print(f"DEBUG: 학생 {student_profile.name} / 총 할당된 통합 활동: {all_activities.count()}건")

    return render(request, 'activities/student_dashboard.html', {
        'activities': all_activities, # 변수명 통합
        'student': student_profile,
    })

# 교과 논술형 평가 목록 보기
@login_required
@teacher_required
def activity_list(request):
    # category='ESSAY' (또는 모델에 설정한 교과평가용 코드)만 필터링합니다.
    activities = Activity.objects.filter(
        teacher=request.user, 
        category='ESSAY'  # 이 부분을 추가하세요
    ).order_by('-created_at')
    
    return render(request, 'activities/activity_list.html', {'activities': activities})

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

# 2. 평가 생성
@login_required
@teacher_required
def create_test(request):
    if request.method == 'POST':
        a_form = ActivityForm(request.POST)
        q_form = QuestionForm(request.POST)
        
        # 선택된 학생 ID 리스트
        selected_student_ids = request.POST.getlist('target_students')

        if a_form.is_valid() and q_form.is_valid():
            activity = a_form.save(commit=False)
            activity.teacher = request.user
        
            # 1. 카테고리 고정 (교과 논술형)
            activity.category = 'ESSAY'
            
            # 2. 작성 분량 (안전하게 숫자로 변환)
            char_limit_raw = request.POST.get('char_limit', '').strip()
            activity.char_limit = int(char_limit_raw) if char_limit_raw else 0
            
            # 3. 응시 환경 유형
            activity.exam_mode = request.POST.get('exam_mode', 'CLOSED')
            
            activity.save() # 이제 모든 필드가 포함되어 저장됨
            
            # 학생 연결
            if selected_student_ids:
                activity.target_students.set(selected_student_ids)

            question = q_form.save(commit=False)
            question.activity = activity
            question.save()
            
            messages.success(request, "평가가 성공적으로 생성되었습니다.")
            return redirect('activity_list')
    else:
        initial_subject = {'subject_name': request.user.subject.name if request.user.subject else ''}
        a_form = ActivityForm(initial=initial_subject)
        q_form = QuestionForm()
        
    student_tree = get_student_tree(request.user)
    
    return render(request, 'activities/create_test.html', {
        'a_form': a_form, 'q_form': q_form, 'action': '생성',
        'student_tree': student_tree
    })

# 3. 평가/활동 수정
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
                clean_dt = dt_str.replace('오후', 'PM').replace('오전', 'AM')
                naive_dt = datetime.strptime(clean_dt, "%Y. %m. %d. %p %I:%M")
                return make_aware(naive_dt)
            except: return None

        # ------------------------------------------------
        # 3. [핵심 수정] 데이터 업데이트 (실제 DB 반영)
        # ------------------------------------------------
        
        # [섹션 1: 기본 정보]
        activity.section = request.POST.get('section', activity.section)
        activity.title = request.POST.get('title', activity.title)
        activity.exam_mode = request.POST.get('exam_mode', 'CLOSED')
        
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
        activity.q1_title = request.POST.get('q1_title', activity.q1_title)
        activity.q2_title = request.POST.get('q2_title', activity.q2_title)
        activity.q3_title = request.POST.get('q3_title', activity.q3_title)
        
        # 날짜 업데이트
        if request.POST.get('activity_date'):
            activity.activity_date = parse_dt(request.POST.get('activity_date'))
        if request.POST.get('deadline'):
            activity.deadline = parse_dt(request.POST.get('deadline'))

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

        # 6. 학생 매칭 업데이트
        target_ids = request.POST.getlist('target_students')
        if target_ids:
            activity.target_students.set(target_ids)

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

# 4. 평가 삭제
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
    # 이렇게 해야 동아리 삭제 후 다시 동아리 목록이 나옵니다.
    return redirect(f'/activities/list/?category={cat_code}&sub={sub_menu}')

# 5. 평가 상태 토글 (시작 <-> 마감)
@login_required
@teacher_required
def toggle_activity_status(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    
    # 상태 뒤집기 (True <-> False)
    activity.is_active = not activity.is_active
    activity.save()

    status_msg = "평가가 [시작]되었습니다." if activity.is_active else "평가가 [마감]되었습니다."
    messages.success(request, status_msg)

    # 활동의 카테고리에 따라 원래 목록 페이지로 리다이렉트
    return redirect(f'/activities/list/?category={activity.category}&sub={activity.sub_category}')

# 6. 평가 상세 페이지 (여기서 수정/삭제 가능)
@login_required
@teacher_required
def activity_detail(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    # URL에서 받은 sub_menu 정보를 바탕으로 config 가져오기
    sub_menu = request.GET.get('sub', activity.sub_category)
    config = get_form_config(sub_menu) # 템플릿에서 조건부로 특정 영역 보이게 할 때 사용
    questions = activity.questions.all()
    return render(request, 'activities/activity_detail.html', {'activity': activity, 'questions': questions, 'config': config})

# 7. 제출 현황(답안) 보기 페이지
@login_required
@teacher_required
def activity_result(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    
    # 1. 평가 '대상 학생(Target)' 가져오기
    # (만약 대상 학생이 0명이면, 혹시 모르니 선생님 전체 학생을 가져오는 안전장치 추가 가능)
    all_students = activity.target_students.all().order_by('grade', 'class_no', 'number')
    
    # 대상자가 한 명도 없으면(예전 데이터) -> 기존대로 선생님 학생 전체 가져오기 (호환성 유지)
    if not all_students.exists():
        all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')

    # 2. 필터 데이터 만들기 (파이썬 기본 문법 사용 - 가장 안전함!)
    # 복잡한 DB 기능 대신, 직접 리스트를 만듭니다.
    temp_data = {}
    for s in all_students:
        g = s.grade
        c = s.class_no
        if g not in temp_data:
            temp_data[g] = []
        if c not in temp_data[g]:
            temp_data[g].append(c)
    
    # 리스트로 변환 (HTML에서 쓰기 좋게 가공)
    filter_data = []
    for g in sorted(temp_data.keys()):
        # 반 목록 정렬 및 중복 제거
        sorted_classes = sorted(list(set(temp_data[g])))
        filter_data.append({
            'grade': g,
            'classes': sorted(list(set(temp_data[g])))
        })

    # 3. 검색 조건 처리
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')

    # 4. 초기값 설정 (1학년 1반 자동 선택)
    # 데이터가 있으면 첫 번째 학년/반을 기본값으로
    if not selected_targets and not name_query and filter_data:
        g = filter_data[0]['grade']
        c = filter_data[0]['classes'][0]
        selected_targets = [f"{g}_{c}"]

    # 5. 필터링 (안전하게 처리)
    target_students = all_students

    if selected_targets:
        q_objects = Q()
        for t in selected_targets:
            if '_' in t: # 안전장치: 형식이 맞을 때만 처리
                g, c = t.split('_')
                q_objects |= Q(grade=g, class_no=c)
        target_students = target_students.filter(q_objects)

    if name_query:
        target_students = target_students.filter(name__contains=name_query)

    # 6. 제출 현황 정리
    submission_list = []
    question = activity.questions.first()

    for student in target_students:
        answer = Answer.objects.filter(student=student, question=question).first()
        status = "미응시"
        submitted_at = "-"
        answer_id = None
        note = ""
        absence = ""

        log_data = ""
        if answer:
            answer_id = answer.id
            note = answer.note
            absence = answer.absence_type
            log_data = answer.activity_log 
            if answer.content.strip():
                status = "제출 완료"
                submitted_at = answer.submitted_at
            elif absence:
                status = "결시"
            else:
                status = "미응시"
        
        submission_list.append({
            'student': student,
            'status': status,
            'submitted_at': submitted_at,
            'answer_id': answer_id,
            'note': note,
            'absence': absence,
            'activity_log': log_data,
        })

    context = {
        'activity': activity,
        'submission_list': submission_list,
        'filter_data': filter_data,
        'selected_targets': selected_targets,
        'current_q': name_query,
    }
    return render(request, 'activities/activity_result.html', context)

# 8. 학생 응시 페이지
@login_required
def take_test(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id)

    # 1. 학생 권한 및 활성화 체크
    if request.user.role != 'STUDENT' or not activity.is_active:
        messages.error(request, "접근할 수 없는 평가입니다.")
        return redirect('dashboard')

    # 2. 내 학생 정보 가져오기
    student_info = Student.objects.filter(email=request.user.email).first()
    if not student_info:
        messages.error(request, "학생 정보를 찾을 수 없습니다.")
        return redirect('dashboard')

    # 3. 내가 평가 대상자가 맞는지 확인 (보안)
    if student_info not in activity.target_students.all():
        messages.error(request, "본인의 평가 대상이 아닙니다.")
        return redirect('dashboard')

    # 4. 문항(Question) 가져오기 (통합 로직: 없으면 자동 생성)
    # activity.questions.first()가 있으면 가져오고, 없으면 defaults의 내용으로 새로 만듭니다.
    question, q_created = Question.objects.get_or_create(
        activity=activity,
        defaults={
            'content': activity.question,
            'conditions': activity.conditions,
            'reference': activity.reference_material # Question 모델은 필드명이 'reference'입니다.
        }
    )

    # 5. [핵심] 답안지(Answer) 껍데기 생성/가져오기
    # 이 시점에 Answer 객체가 확실히 생성되므로 대시보드에서 '작성 중'으로 인지하게 됩니다.
    answer, a_created = Answer.objects.get_or_create(
        student=student_info,
        question=question
    )

    # 6. 최초 진입 시간 기록 (처음 생성된 경우에만 로그 기록)
    if a_created:
        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        answer.activity_log = f"[{timestamp}] 시험 시작 (최초 진입)\n"
        answer.save()

    if request.method == 'POST':
        # 제출인지 임시저장인지 구분 (hidden 필드 'is_submit' 기준)
        is_final_submit = request.POST.get('is_submit') == 'true'

        # 6. 답안 제출 처리 (이미 생성된 객체에 내용만 업데이트)
        # 6-1. 항목별 답변 가져오기
        answer.ans_q1 = request.POST.get('ans_q1', '').strip()
        answer.ans_q2 = request.POST.get('ans_q2', '').strip()
        answer.ans_q3 = request.POST.get('ans_q3', '').strip()
        
        # 합본 생성 로직
        answer.content = f"[{activity.q1_title}]\n{answer.ans_q1}\n\n[{activity.q2_title}]\n{answer.ans_q2}\n\n[{activity.q3_title}]\n{answer.ans_q3}"
        
        # 최종 제출일 때만 제출 시간 기록 및 로그 남기기
        if is_final_submit:
            answer.submitted_at = timezone.now()
            timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            answer.activity_log += f"[{timestamp}] 답안 최종 제출 완료\n"

        answer.save()
        
        if is_final_submit:
            messages.success(request, "답안이 제출되었습니다.")
            return redirect('dashboard')
        else:
            return JsonResponse({'status': 'success', 'message': '임시 저장 완료'})

    # 7. 화면에 데이터 전달
    return render(request, 'activities/take_test.html', {
        'activity': activity,
        'answer': answer, # 기존 답안 전달
        'answer_id': answer.id,
    })

# 9. 결시 사유 업데이트 API (AJAX용)
@login_required
@teacher_required
def update_absence(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            student_id = data.get('student_id')
            activity_id = data.get('activity_id')
            absence_value = data.get('value')

            activity = get_object_or_404(Activity, id=activity_id)
            question = activity.questions.first()
            student = get_object_or_404(Student, id=student_id)

            # 1. 답안지가 있는지 확인
            answer = Answer.objects.filter(student=student, question=question).first()

            if not answer:
                # 2. 없으면 새로 생성 (이때 content를 ' ' 공백으로라도 채워줍니다)
                answer = Answer.objects.create(
                    student=student,
                    question=question,
                    content=" ", # 빈 문자열 대신 공백 하나 넣어서 에러 방지
                    absence_type=absence_value
                )
            else:
                # 3. 있으면 결시 사유만 업데이트
                answer.absence_type = absence_value
                answer.save()
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'fail'})

# 10. 답안 상세, 삭제, 메모 저장 (추가 필요 시 여기에)
@login_required
@teacher_required
def answer_detail(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id)
    return render(request, 'activities/answer_detail.html', {'answer': answer})

@login_required
@teacher_required
def answer_delete(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id)
    activity = answer.question.activity
    
    # 리다이렉트 시 필요한 정보 미리 보관
    activity_id = activity.id
    cat = request.GET.get('category', activity.category)
    sub = request.GET.get('sub', activity.sub_category)
    
    # 답안 삭제
    answer.delete()
    
    messages.success(request, "답안을 삭제(반려)했습니다.")
    
    # 제출 현황으로 돌아갈 때 파라미터를 함께 전달하여 메뉴 활성화 유지
    return redirect(f'/activities/result/{activity_id}/?category={cat}&sub={sub}')

@login_required
@teacher_required
def save_note(request, answer_id):
    if request.method == 'POST':
        answer = get_object_or_404(Answer, id=answer_id)
        answer.note = request.POST.get('note', '')
        answer.save()
        messages.success(request, "특이사항 저장 완료.")
        return redirect('activity_result', activity_id=answer.question.activity.id)
    return redirect('dashboard')

# 학생 활동 로그 저장 API
@login_required
def log_activity(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            answer_id = data.get('answer_id')
            action_type = data.get('type') # 'OUT'(이탈) 또는 'IN'(복귀)
            log_type = data.get('type')
            
            answer = Answer.objects.get(id=answer_id)
            
            # 기존 로그에 새로운 기록 추가 (줄바꿈 포함)
            current_log = answer.activity_log if answer.activity_log else ""
            timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 로그 메시지 매핑
            log_messages = {
                'OUT': '화면 이탈(Alt+Tab 또는 창 전환)',
                'IN': '화면 복귀',
                'COPY': '복사 시도',
                'PASTE': '붙여넣기 시도',
                'RIGHT_CLICK': '우클릭 시도',
                'EXIT': '중도 퇴장',
                'BACK_BUTTON': '브라우저 뒤로가기 버튼 클릭 시도'
            }
            
            new_entry = f"[{timestamp}] {log_messages.get(log_type, log_type)}\n"
            answer.activity_log = current_log + new_entry
            answer.save()
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)

# 11. 결과 분석 페이지
@login_required
@teacher_required
def activity_analysis(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    question = activity.questions.first() # 현재는 단일 문항 가정

    # 1. 평가 대상 학생 가져오기 (지정된 학생만)
    all_students = activity.target_students.all().order_by('grade', 'class_no', 'number')
    
    # 대상이 없으면 선생님 전체 학생으로 대체 (호환성)
    if not all_students.exists():
        all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')

    # 2. 필터 데이터 생성 (학년/반 트리)
    temp_dict = {}
    for s in all_students:
        g = s.grade
        c = s.class_no
        if g not in temp_dict: temp_dict[g] = []
        if c not in temp_dict[g]: temp_dict[g].append(c)
    
    filter_data = []
    for g in sorted(temp_dict.keys()):
        filter_data.append({'grade': g, 'classes': sorted(list(set(temp_dict[g])))})

    # 3. 검색 조건 처리
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')

    # 4. [최적화] 초기 진입 시 '1학년 1반' 강제 선택
    if not selected_targets and not name_query:
        if filter_data:
            g = filter_data[0]['grade']
            c = filter_data[0]['classes'][0]
            selected_targets = [f"{g}_{c}"]

    # 5. 필터링 적용
    target_students = all_students
    if selected_targets:
        q_objects = Q()
        for t in selected_targets:
            try:
                g, c = t.split('_')
                q_objects |= Q(grade=g, class_no=c)
            except: pass
        target_students = target_students.filter(q_objects)

    if name_query:
        target_students = target_students.filter(name__contains=name_query)

    # 6. 분석용 데이터 리스트 생성
    # (제출 현황과 달리, 여기서는 '답안 내용'이 중요합니다)
    analysis_list = []
    
    for student in target_students:
        answer = Answer.objects.filter(student=student, question=question).first()
        
        content = ""
        submitted_at = ""
        ai_result = ""
        has_answer = False

        if answer:
            content = answer.content
            submitted_at = answer.submitted_at
            ai_result = answer.ai_result
            has_answer = True
        
        analysis_list.append({
            'student': student,
            'has_answer': has_answer,
            'content': content,
            'submitted_at': submitted_at,
            'ai_result': ai_result,
        })

    context = {
        'activity': activity,
        'question': question,
        'analysis_list': analysis_list,
        'filter_data': filter_data,
        'selected_targets': selected_targets,
        'current_q': name_query,
    }
    return render(request, 'activities/activity_analysis.html', context)

# 12. 종합 분석 (모든 평가 모아보기)
@login_required
@teacher_required
def integrated_analysis(request):
    # 1. 필터링을 위한 전체 학생 가져오기 (기존 로직 재사용)
    all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')
    
    # --- 필터 데이터 생성 (기존과 동일) ---
    temp_dict = {}
    for s in all_students:
        g = s.grade
        c = s.class_no
        if g not in temp_dict: temp_dict[g] = []
        if c not in temp_dict[g]: temp_dict[g].append(c)
    
    filter_data = []
    for g in sorted(temp_dict.keys()):
        filter_data.append({'grade': g, 'classes': sorted(list(set(temp_dict[g])))})
    
    # 2. 검색 조건 처리
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')

    # 초기값 설정 (1학년 1반)
    if not selected_targets and not name_query and filter_data:
        g = filter_data[0]['grade']
        c = filter_data[0]['classes'][0]
        selected_targets = [f"{g}_{c}"]

    # 필터링 적용
    target_students = all_students
    if selected_targets:
        q_objects = Q()
        for t in selected_targets:
            if '_' in t:
                g, c = t.split('_')
                q_objects |= Q(grade=g, class_no=c)
        target_students = target_students.filter(q_objects)
    if name_query:
        target_students = target_students.filter(name__contains=name_query)

    # ----------------------------------------------------
    # ★ [핵심] 가로축(열) 만들기: 선생님이 만든 모든 평가 가져오기
    activities = Activity.objects.filter(teacher=request.user).order_by('created_at')
    
    # ★ [핵심] 데이터 매트릭스 만들기 (학생 x 평가)
    analysis_table = []
    
    for student in target_students:
        row_data = {
            'student': student,
            'answers': [] # 평가 순서대로 답안을 채워 넣음
        }
        
        for act in activities:
            # 해당 평가의 첫 번째 질문에 대한 이 학생의 답안 찾기
            question = act.questions.first()
            if question:
                ans = Answer.objects.filter(student=student, question=question).first()
                if ans:
                    # 내용이 있으면 내용, 없으면 결시 사유 등 표시
                    row_data['answers'].append(ans.content if ans.content.strip() else f"({ans.get_absence_type_display()})")
                else:
                    row_data['answers'].append("") # 미응시 (빈칸)
            else:
                row_data['answers'].append("-") # 질문 없음
                
        analysis_table.append(row_data)

    context = {
        'filter_data': filter_data,
        'selected_targets': selected_targets,
        'current_q': name_query,
        'activities': activities,   # 헤더(가로축)
        'analysis_table': analysis_table # 본문(데이터)
    }
    return render(request, 'activities/integrated_analysis.html', context)

# 분석 작업 메인 페이지
@login_required
@teacher_required
def activity_analysis_work(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    question = activity.questions.first()
    
    answer_list = [] # 기본값은 빈 리스트
    
    # 질문이 존재할 때만 답안을 찾음
    if question:
        # content가 비어있지 않은(공백 제외) 답안만 가져옵니다.
        answers = Answer.objects.filter(
            question=question
        ).exclude(content__set='').select_related('student') # 실제 내용이 있는 것만!

        for a in answers:
            if a.content and a.content.strip():
                answer_list.append({
                    'id': a.id,
                    'name': a.student.name,
                    'info': f"{a.student.grade}-{a.student.class_no}-{a.student.number}"
                })

    # 만약 answer_list가 비어있다면 명시적으로 '[]' 문자열을 만듦
    answer_list_json = json.dumps(answer_list) if answer_list else "[]"

    context = {
        'activity': activity,
        'question': question,
        'submit_count': len(answer_list),
        'answer_list_json': answer_list_json, # 이제 무조건 '[]' 라도 나감
        'prompt_templates': PromptTemplate.objects.all(),
        'length_options': PromptLengthOption.objects.all(),
    }
    return render(request, 'activities/activity_analysis_work.html', context)

# DB 답안을 하나씩 AI에게 보내는 로직
@csrf_exempt
@login_required
def api_process_db_row(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            answer_id = body.get('answer_id')
            prompt_system = body.get('prompt_system')
            temperature = float(body.get('temperature', 0.7))
            ai_model = body.get('ai_model', 'gemini-2.0-flash')

            # 1. 답안 및 활동 정보 가져오기
            answer = Answer.objects.get(id=answer_id)
            activity = answer.question.activity # 역참조로 활동 정보 획득
            student = answer.student
            
            # 답안이 비어있으면 AI 호출 없이 리턴
            if not answer.content or not answer.content.strip():
                return JsonResponse({
                    'status': 'skipped', 
                    'message': '내용이 없는 답안은 분석하지 않습니다.'
                })

            # 2. [추가 피드백 반영] 프롬프트에 활동 상세 정보 통합
            # AI에게 "문제와 조건"을 먼저 알려주어 분석 정확도를 높입니다.
            activity_context = f"""
[활동 정보 및 컨텍스트]
- 활동명: {activity.section}
- 평가 주제: {activity.title}
- 평가 문항: {activity.question}
- 참고 자료: {activity.reference_material}
- 작성 조건: {activity.conditions}
- 권장 분량: {activity.char_limit}자 이상
"""
            student_info = f"[대상 학생: {student.name}({student.grade}-{student.class_no}-{student.number})]"
            
            # 최종 지시사항 조립 (활동 정보 + 학생 답안 + 교사 지시사항)
            final_prompt = f"{activity_context}\n{student_info}\n[학생 답안 내용]\n{answer.content}\n\n[AI 지시사항]\n{prompt_system}"
            
            # ---------------------------------------------------------
            # Google Gemini 2.0 Flash 호출 (기존 로직 유지)
            # ---------------------------------------------------------
            config = SystemConfig.objects.get(key_name='GOOGLE_API_KEY')
            api_key = config.value.strip()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{ai_model}:generateContent?key={api_key}"
            
            payload = {
                "contents": [{"parts": [{"text": final_prompt}]}],
                "generationConfig": {"temperature": temperature}
            }
            
            response = requests.post(url, json=payload, timeout=60)
            
            # [추가 피드백 반영] 429 에러 처리 로직 강화
            if response.status_code == 429:
                return JsonResponse({
                    'status': 'error', 
                    'message': 'AI 서버가 너무 바쁩니다(429). 잠시 후 다시 시도해 주세요.'
                }, status=429)

            response_data = response.json()
            
            if "candidates" in response_data:
                result_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                # 에러 발생 시 상세 메시지 기록
                result_text = f"[Google API 에러] {response_data}"

            # 3. ★ DB에 분석 결과 저장 ★
            answer.ai_result = result_text
            answer.ai_updated_at = timezone.now() # AI 분석 일시 기록
            answer.save()
            
            return JsonResponse({'status': 'success', 'result': '저장 완료'})
            
        except SystemConfig.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': '관리자 페이지에서 GOOGLE_API_KEY를 등록해주세요.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'fail'}, status=400)

# 1. 창의적체험활동 목록 뷰
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

# 2. 창의적체험활동 생성 뷰
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
        exam_mode = request.POST.get('exam_mode', 'CLOSED')
        
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
            is_active=True
        )

        # 3. 자율활동용 문항(Question) 자동 생성 (답안 제출 에러 방지)
        from .models import Question
        Question.objects.create(
            activity=activity,
            content=question,
            conditions=conditions,
        )

        # 4. 학생 등록
        target_ids = request.POST.getlist('target_students')
        if target_ids:
            activity.target_students.set(target_ids)
            
        return redirect('creative_list')

    # GET 요청 시
    student_tree = get_student_tree(request.user)
    return render(request, 'activities/creative_form.html', {
        'sub_menu': sub_menu,
        'student_tree': student_tree,
        'action': '생성'
    })

# 상세 페이지
@login_required
def creative_detail(request, pk):
    activity = get_object_or_404(Activity, pk=pk, teacher=request.user)
    return render(request, 'activities/creative_detail.html', {'activity': activity})

# 수정 페이지
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
            
        # 날짜 처리
        deadline_str = request.POST.get('deadline')
        if deadline_str:
            try:
                # 오후/오전 한글 대응
                temp_str = deadline_str.replace('오후', 'PM').replace('오전', 'AM')
                activity.deadline = datetime.strptime(temp_str, "%Y. %m. %d. %p %I:%M")
            except:
                pass

        # 시험 모드 설정
        activity.exam_mode = request.POST.get('exam_mode', 'CLOSED')
            
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
            activity.target_students.set(target_ids)
            
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

# 삭제 처리
@login_required
def creative_delete(request, pk):
    activity = get_object_or_404(Activity, pk=pk, teacher=request.user)
    if request.method == 'POST':
        activity.delete()
        return redirect('creative_list')
    return redirect('creative_detail', pk=pk)

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

# 통합 생성/수정 페이지 (카테고리와 소메뉴에 따라 유동적으로 필드 라벨과 저장 로직 변경)
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

# 통합 생성 페이지 (카테고리와 소메뉴에 따라 유동적으로 필드 라벨과 저장 로직 변경)
@login_required
def unified_create(request):
    # 1. URL 파라미터에서 정보 가져오기
    cat_code = request.GET.get('category', 'ESSAY')
    sub_menu = request.GET.get('sub', '과목별 수행평가')
    
    # 메뉴별 설정 가져오기
    config = get_form_config(sub_menu)
    category_name = dict(Activity.CATEGORY_CHOICES).get(cat_code, "평가/활동")

    if request.method == 'POST':
        # [내부 함수] 날짜 파싱
        def parse_dt(dt_str):
            if not dt_str: return None
            try:
                clean_dt = dt_str.replace('오후', 'PM').replace('오전', 'AM')
                naive_dt = datetime.strptime(clean_dt, "%Y. %m. %d. %p %I:%M")
                return make_aware(naive_dt)
            except: return None

        # [수정: 섹션 2 평가 문항 처리] 
        # 루프 방식 대신 HTML의 name="question"에서 직접 가져와 유실을 방지합니다.
        main_question = request.POST.get('question', '').strip()
        
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

        try:
            # --- [Activity 객체 생성] ---
            activity = Activity.objects.create(
                teacher=request.user,
                category=cat_code,
                sub_category=sub_menu,
                
                # [섹션 1: 기본 정보]
                section=request.POST.get('section', sub_menu),
                title=request.POST.get('title', '제목 없음') + extra_str,
                exam_mode=request.POST.get('exam_mode', 'CLOSED'),
                deadline=parse_dt(request.POST.get('deadline')), # 섹션 1 기한
                
                # [섹션 2: 세부 평가 내용]
                activity_date=parse_dt(request.POST.get('activity_date')),
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
                
                is_active=True
            )

            # --- [다중 파일 저장] ---
            files = request.FILES.getlist('attachments')
            for f in files:
                ActivityFile.objects.create(activity=activity, file=f)

            # --- [후속 처리] ---
            # 1. Question 객체 생성 (Answer 모델과의 연결을 위해 필수)
            from .models import Question
            Question.objects.create(
                activity=activity, 
                content=main_question, # Activity와 동일한 내용 복사
                conditions=activity.conditions
            )

            # 2. 대상 학생 등록
            target_ids = request.POST.getlist('target_students')
            if target_ids:
                activity.target_students.set(target_ids)

            messages.success(request, f"'{sub_menu}' 시트가 성공적으로 생성되었습니다.")
            return redirect(f'/activities/list/?category={cat_code}&sub={sub_menu}')

        except Exception as e:
            logger.error(f"생성 에러: {str(e)}")
            messages.error(request, f"저장 중 오류가 발생했습니다: {str(e)}")
            return redirect(request.path + f"?category={cat_code}&sub={sub_menu}")

    # 7. GET 요청 시
    return render(request, 'activities/unified_form.html', {
        'cat_code': cat_code, 
        'sub_menu': sub_menu, 
        'config': config,
        'student_tree': get_student_tree(request.user),
        'action': '생성'
    })