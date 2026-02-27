from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.decorators import teacher_required
from django.contrib import messages
from django.utils import timezone # 날짜 표시용
from datetime import datetime   # 날짜 비교용
from django.db.models import Q  # 복합 필터링
import json
import requests
import random
import openai
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 모델과 폼 가져오기
from .models import Activity, Question, Answer
from .forms import ActivityForm, QuestionForm, AnswerForm
from accounts.models import Student, SystemConfig, PromptTemplate, PromptCategory, PromptLengthOption
import logging
logger = logging.getLogger(__name__)

# 1. 학생 대시보드 (응시 가능한 평가 목록)
@login_required
def student_dashboard(request):
    # 1. 학생 객체 찾기 (이메일 기반으로 찾는 것이 가장 정확함)
    student_profile = Student.objects.filter(email=request.user.email).first()
    
    if not student_profile:
        # 이메일로 못 찾으면 연결된 프로필로 재시도
        student_profile = getattr(request.user, 'student', None)

    if not student_profile:
        return render(request, 'activities/student_dashboard.html', {
            'essay_activities': [], 'creative_activities': []
        })

    # 2. 이 학생에게 할당된 모든 활동 가져오기 (상태 필터 일단 제거하여 데이터 확인)
    all_assigned = Activity.objects.filter(target_students=student_profile)

    # 3. 카테고리 분류 (핵심 수정: 공백이나 오타를 방지하기 위해 icontains 사용)
    # 쉘에서 발견된 'ESSAY ' 문제를 해결하기 위해 포함(icontains) 방식으로 필터링합니다.
    essay_activities = all_assigned.filter(category__icontains='ESSAY').order_by('-created_at')
    creative_activities = all_assigned.filter(category__icontains='CREATIVE').order_by('-created_at')

    # (디버깅용 출력: 가비아 터미널에서 확인 가능)
    print(f"DEBUG: 학생 {student_profile.name} / 총 할당: {all_assigned.count()} / 논술형: {essay_activities.count()} / 자율: {creative_activities.count()}")

    return render(request, 'activities/student_dashboard.html', {
        'essay_activities': essay_activities,
        'creative_activities': creative_activities,
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

# 3. 평가 수정
@login_required
@teacher_required
def update_test(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    question = activity.questions.first() 

    if request.method == 'POST':
        a_form = ActivityForm(request.POST, instance=activity)
        q_form = QuestionForm(request.POST, instance=question)
        selected_student_ids = request.POST.getlist('target_students')

        if a_form.is_valid() and q_form.is_valid():
            # [중요] 수정 시에도 수동 필드 업데이트 필요
            activity = a_form.save(commit=False)
            
            # 작성 분량 처리
            char_limit_raw = request.POST.get('char_limit', '').strip()
            activity.char_limit = int(char_limit_raw) if char_limit_raw else 0
            
            # 응시 환경 유형 처리
            activity.exam_mode = request.POST.get('exam_mode', 'CLOSED')
            
            activity.save() # 변경사항 반영
            
            # 학생 대상 업데이트
            activity.target_students.set(selected_student_ids)
            q_form.save()
            
            messages.success(request, "평가 정보가 수정되었습니다.")
            return redirect('activity_list')
    else:
        a_form = ActivityForm(instance=activity)
        q_form = QuestionForm(instance=question)

    student_tree = get_student_tree(request.user)
    current_targets = list(activity.target_students.values_list('id', flat=True))

    return render(request, 'activities/create_test.html', {
        'a_form': a_form, 'q_form': q_form, 'action': '수정',
        'student_tree': student_tree,
        'current_targets': current_targets,
        'activity': activity # 템플릿에서 activity.exam_mode 등을 참조하기 위해 추가
    })

# 4. 평가 삭제
@login_required
@teacher_required
def delete_test(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    activity.delete()
    messages.success(request, "평가가 삭제되었습니다.")
    return redirect('activity_list')

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
    if activity.category == 'CREATIVE':
        return redirect('creative_list') # 창체 목록으로 이동
    else:
        return redirect('activity_list') # 교과 평가 목록으로 이동

# 6. 평가 상세 페이지 (여기서 수정/삭제 가능)
@login_required
@teacher_required
def activity_detail(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    questions = activity.questions.all()
    return render(request, 'activities/activity_detail.html', {'activity': activity, 'questions': questions})

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

        if answer:
            answer_id = answer.id
            note = answer.note
            absence = answer.absence_type
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

    # 4. 문항(Question) 가져오기 및 자율활동 예외 처리
    # (자율활동은 문항 객체가 없을 수 있으므로 즉석 생성하여 IntegrityError 방지)
    question = activity.questions.first()
    if not question and activity.category == 'CREATIVE':
        from .models import Question
        question = Question.objects.create(
            activity=activity,
            content=activity.question,
            conditions=activity.conditions,
            reference_material=activity.reference_material
        )

    # 5. [핵심] 답안지(Answer) 껍데기 미리 생성/가져오기
    # 페이지 접속 시점에 만들어둬야 실시간 이탈 로그(AJAX)를 기록할 수 있습니다.
    answer, created = Answer.objects.get_or_create(
        student=student_info,
        question=question
    )

    if request.method == 'POST':
        # 6. 답안 제출 처리 (이미 생성된 객체에 내용만 업데이트)
        content = request.POST.get('content', '').strip()
        if not content:
            messages.error(request, "내용을 입력해주세요.")
        else:
            answer.content = content
            answer.submitted_at = timezone.now() # 제출 시간 기록
            answer.save()
            messages.success(request, "답안이 제출되었습니다!")
            return redirect('dashboard')

    # 7. 화면에 데이터 전달
    context = {
        'activity': activity,
        'question': question,
        'answer_id': answer.id,  # JS에서 로그 보낼 때 쓸 ID
        'existing_content': answer.content, # 작성 중이던 내용 복구용
        'today': timezone.now()
    }
    return render(request, 'activities/take_test.html', context)

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
    activity_id = answer.question.activity.id
    answer.delete()
    messages.success(request, "답안을 삭제(반려)했습니다.")
    return redirect('activity_result', activity_id=activity_id)

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
        answers = Answer.objects.filter(question=question).select_related('student')
        for a in answers:
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
            
            # ★ 모델명을 gemini-2.0-flash 로 고정하거나 기본값으로 설정
            ai_model = body.get('ai_model', 'gemini-2.0-flash')

            # 1. 답안 데이터 가져오기
            answer = Answer.objects.get(id=answer_id)
            student = answer.student
            
            # 2. 프롬프트 재료 조합
            student_info = f"[학생: {student.name}({student.grade}-{student.class_no}-{student.number})]"
            # 최종 지시사항 조립
            final_prompt = f"{student_info}\n[학생 답안]\n{answer.content}\n\n[지시사항]\n{prompt_system}"
            
            result_text = ""

            # ---------------------------------------------------------
            # Google Gemini 2.0 Flash 호출 로직 (REST API 방식)
            # ---------------------------------------------------------
            config = SystemConfig.objects.get(key_name='GOOGLE_API_KEY')
            api_key = config.value.strip()
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{ai_model}:generateContent?key={api_key}"
            
            payload = {
                "contents": [{
                    "parts": [{"text": final_prompt}]
                }],
                "generationConfig": {
                    "temperature": temperature
                }
            }
            
            # 구글 서버로 직접 요청
            response = requests.post(url, json=payload)
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
    if request.method == 'POST':
        
        # 1. 폼 데이터 먼저 모두 받아오기 (변수에 담기)
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