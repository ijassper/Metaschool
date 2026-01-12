from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.decorators import teacher_required
from accounts.models import Student
from .models import Activity, Question, Answer
from .forms import ActivityForm, QuestionForm, AnswerForm
from django.contrib import messages
from django.utils import timezone # 날짜 표시용
from django.http import JsonResponse
from django.db.models import Q  # 복합 필터링
import json

# 1. 내가 만든 평가 목록 보기
@login_required
@teacher_required
def activity_list(request):
    # 최신순으로 정렬해서 가져오기
    activities = Activity.objects.filter(teacher=request.user).order_by('-created_at')
    return render(request, 'activities/activity_list.html', {'activities': activities})

# 2. 평가 생성 (과목명 수동 입력 반영)
@login_required
@teacher_required
def create_test(request):
    if request.method == 'POST':
        a_form = ActivityForm(request.POST)
        q_form = QuestionForm(request.POST)
        
        if a_form.is_valid() and q_form.is_valid():
            activity = a_form.save(commit=False)
            activity.teacher = request.user
            # activity.subject_name = ... (이 줄 삭제! 폼에서 입력받은 값 그대로 씀)
            activity.save()
            
            question = q_form.save(commit=False)
            question.activity = activity
            question.save()
            
            messages.success(request, "평가가 생성되었습니다.")
            return redirect('activity_list') # 생성 후 목록으로 이동
    else:
        # 과목명 기본값으로 선생님 담당과목 넣어주기 (편의성)
        initial_subject = {'subject_name': request.user.subject.name if request.user.subject else ''}
        a_form = ActivityForm(initial=initial_subject)
        q_form = QuestionForm()
        
    return render(request, 'activities/create_test.html', {'a_form': a_form, 'q_form': q_form, 'action': '생성'})

# 3. 평가 수정
@login_required
@teacher_required
def update_test(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    # 현재 구조상 Activity 하나당 Question 하나라고 가정하고 첫 번째 질문을 가져옴
    question = activity.questions.first() 

    if request.method == 'POST':
        a_form = ActivityForm(request.POST, instance=activity)
        q_form = QuestionForm(request.POST, instance=question)
        if a_form.is_valid() and q_form.is_valid():
            a_form.save()
            q_form.save()
            messages.success(request, "평가가 수정되었습니다.")
            return redirect('activity_list')
    else:
        a_form = ActivityForm(instance=activity)
        q_form = QuestionForm(instance=question)

    # 생성 페이지(create_test.html)를 재활용하되 action 변수로 구분
    return render(request, 'activities/create_test.html', {'a_form': a_form, 'q_form': q_form, 'action': '수정'})

# 4. 평가 삭제
@login_required
@teacher_required
def delete_test(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    activity.delete()
    messages.success(request, "평가가 삭제되었습니다.")
    return redirect('activity_list')

# [신규] 1. 평가 상태 토글 (시작 <-> 마감)
@login_required
@teacher_required
def toggle_activity_status(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    # 상태 뒤집기 (True <-> False)
    activity.is_active = not activity.is_active
    activity.save()
    
    status_msg = "평가가 [시작]되었습니다." if activity.is_active else "평가가 [마감]되었습니다."
    messages.success(request, status_msg)
    return redirect('activity_list')

# [신규] 2. 평가 상세 페이지 (여기서 수정/삭제 가능)
@login_required
@teacher_required
def activity_detail(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    questions = activity.questions.all()
    return render(request, 'activities/activity_detail.html', {'activity': activity, 'questions': questions})

# [신규] 3. 제출 현황(답안) 보기 페이지
@login_required
@teacher_required
def activity_result(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    
    # 1. 선생님의 전체 학생 가져오기 (필터 목록 생성용)
    all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')

    # ★ [디버깅] 학생 수 확인 (이게 0이면 데이터 문제입니다)
    print(f"DEBUG: 선생님({request.user})의 학생 수: {all_students.count()}명", flush=True)
    
    # 학년/반 목록 추출 (중복 제거)
    grade_list = all_students.values_list('grade', flat=True).distinct().order_by('grade')
    class_list = all_students.values_list('class_no', flat=True).distinct().order_by('class_no')

    # 2. 필터용 계층 데이터 만들기 (학년 -> 반)
    # 구조: { 1: [1, 2, 3], 2: [1, 2] } -> 1학년: 1,2,3반 / 2학년: 1,2반
    filter_tree = {}
    for s in all_students:
        # ★ [디버깅] 학생 데이터 하나씩 찍어보기
        # print(f"학생: {s.name} ({s.grade}-{s.class_no})", flush=True) 
        if s.grade not in filter_tree:
            filter_tree[s.grade] = []
        if s.class_no not in filter_tree[s.grade]:
            filter_tree[s.grade].append(s.class_no)
    # ★ [디버깅] 만들어진 트리 확인
    print(f"DEBUG: 생성된 필터 트리: {filter_tree}", flush=True)
    
    # 딕셔너리 정렬 (학년순)
    sorted_filter_tree = dict(sorted(filter_tree.items()))
    for g in sorted_filter_tree:
        sorted_filter_tree[g].sort() # 반순 정렬

    # 3. 검색 조건 가져오기 (다중 선택된 '학년_반' 리스트)
    # 예: ['1_3', '1_4'] -> 1학년 3반, 1학년 4반
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')

    # 4. 초기 진입 시 '1학년 1반' 강제 선택 (필터링 속도 향상)
    # (검색어도 없고, 반 선택도 안 했을 때)
    if not selected_targets and not name_query:
        # 데이터가 있다면 가장 첫 학년, 첫 반을 기본값으로 설정
        if sorted_filter_tree:
            first_grade = list(sorted_filter_tree.keys())[0] # 예: 1학년
            first_class = sorted_filter_tree[first_grade][0] # 예: 1반
            # "1_1" 형태로 타겟 설정
            selected_targets = [f"{first_grade}_{first_class}"]

    # 5. 실제 필터링 적용
    target_students = all_students

    if selected_targets:
        q_objects = Q()
        for target in selected_targets:
            try:
                g, c = target.split('_')
                q_objects |= Q(grade=g, class_no=c)
            except:
                continue
        target_students = target_students.filter(q_objects)
    
    if name_query:
        target_students = target_students.filter(name__contains=name_query)

    # 6. 제출 현황 매칭
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
        'filter_tree': sorted_filter_tree, # ★ 계층형 데이터 전달
        'selected_targets': selected_targets, # ★ 선택된 항목들 전달
        'current_q': name_query,
    }
    return render(request, 'activities/activity_result.html', context)

# 2. 답안 상세 보기 (팝업 또는 새 창)
@login_required
@teacher_required
def answer_detail(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id)
    return render(request, 'activities/answer_detail.html', {'answer': answer})

# 3. 답안 폐기 (삭제)
@login_required
@teacher_required
def answer_delete(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id)
    activity_id = answer.question.activity.id
    answer.delete()
    messages.success(request, "답안을 삭제(반려)했습니다. 학생이 다시 응시할 수 있습니다.")
    return redirect('activity_result', activity_id=activity_id)

# 4. 특이사항 메모 저장 (AJAX 처리 권장하지만, 일단 간단히 Form 처리)
@login_required
@teacher_required
def save_note(request, answer_id):
    if request.method == 'POST':
        answer = get_object_or_404(Answer, id=answer_id)
        answer.note = request.POST.get('note', '')
        answer.save()
        messages.success(request, "특이사항이 저장되었습니다.")
        return redirect('activity_result', activity_id=answer.question.activity.id)
    return redirect('dashboard')

# 학생 평가 응시 페이지
@login_required
def take_test(request, activity_id):
    # 1. 평가 정보 가져오기
    activity = get_object_or_404(Activity, id=activity_id)
    question = activity.questions.first() # 문항 가져오기 (현재는 1개라고 가정)
    
    # [보안] 학생이 아니거나, 평가가 비활성화(준비중) 상태면 튕겨냄
    if request.user.role != 'STUDENT' or not activity.is_active:
        messages.error(request, "접근할 수 없는 평가입니다.")
        return redirect('dashboard')

    # [중복 방지] 이미 제출한 답안이 있는지 확인
    existing_answer = Answer.objects.filter(student__email=request.user.email, question=question).first()
    
    if request.method == 'POST':
        form = AnswerForm(request.POST, instance=existing_answer) # 기존 답안 있으면 수정 모드
        if form.is_valid():
            answer = form.save(commit=False)
            answer.student = Student.objects.get(email=request.user.email) # 내 명부 연결
            answer.question = question
            answer.save()
            
            messages.success(request, "답안이 성공적으로 제출되었습니다!")
            return redirect('dashboard')
    else:
        form = AnswerForm(instance=existing_answer)

    context = {
        'activity': activity,
        'question': question,
        'form': form,
        'today': timezone.now() # 오늘 날짜
    }
    return render(request, 'activities/take_test.html', context)

# 1. [신규] 결시 사유 업데이트 API (AJAX용)
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

            # 답안지 가져오거나 없으면 새로 생성 (빈 답안지)
            answer, created = Answer.objects.get_or_create(
                student=student, 
                question=question,
                defaults={'content': ''} # 내용은 빈칸
            )
            
            # 결시 사유 저장
            answer.absence_type = absence_value
            answer.save()
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'fail'})


# 2. [수정] 제출 현황 조회 (필터 로직 변경 + 결시 정보 전달)
@login_required
@teacher_required
def activity_result(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    
    all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')
    
    grade_list = all_students.values_list('grade', flat=True).distinct().order_by('grade')
    class_list = all_students.values_list('class_no', flat=True).distinct().order_by('class_no')

    # --- [수정된 필터 로직] ---
    current_grade = request.GET.get('grade')
    current_class = request.GET.get('class_no')
    name_query = request.GET.get('q')

    # 1. 학년: 값이 없으면 무조건 '첫 번째 학년'으로 강제 설정 (전체보기 없음)
    if not current_grade:
        if grade_list.exists():
            current_grade = grade_list[0] # 1학년

    # 2. 반: 값이 없으면 '첫 번째 반' 설정 (이름 검색 아닐 때만)
    if not current_class and not name_query:
        if class_list.exists():
            current_class = class_list[0] # 1반

    target_students = all_students.filter(grade=current_grade) # 학년 필터 필수 적용

    if current_class:
        target_students = target_students.filter(class_no=current_class)
    if name_query:
        # 이름 검색 시에는 해당 학년 내에서 검색
        target_students = target_students.filter(name__contains=name_query)
    # -----------------------

    submission_list = []
    question = activity.questions.first()

    for student in target_students:
        answer = Answer.objects.filter(student=student, question=question).first()
        
        status = "미응시"
        submitted_at = "-"
        answer_id = None
        note = ""
        absence = "" # 결시 사유

        if answer:
            answer_id = answer.id
            note = answer.note
            absence = answer.absence_type
            
            # 상태 판단 로직 개선
            if answer.content.strip():
                status = "제출 완료"
                submitted_at = answer.submitted_at
            elif absence:
                status = "결시" # 내용은 없는데 결시 사유가 있으면
            else:
                status = "미응시" # 내용도 없고 결시도 아니면 (데이터만 생성된 경우)

        submission_list.append({
            'student': student,
            'status': status,
            'submitted_at': submitted_at,
            'answer_id': answer_id,
            'note': note,
            'absence': absence, # 템플릿으로 전달
        })

    context = {
        'activity': activity,
        'submission_list': submission_list,
        'grade_list': grade_list,
        'class_list': class_list,
        'current_grade': int(current_grade) if current_grade else '',
        'current_class': int(current_class) if current_class else '',
        'current_q': name_query if name_query else '',
    }
    return render(request, 'activities/activity_result.html', context)