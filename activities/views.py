from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.decorators import teacher_required
from django.contrib import messages
from django.utils import timezone # 날짜 표시용
from django.db.models import Q  # 복합 필터링

# 모델과 폼 가져오기
from .models import Activity, Question, Answer
from .forms import ActivityForm, QuestionForm, AnswerForm
from accounts.models import Student

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
    return redirect('activity_list')

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
    
    # 1. 학생 목록 가져오기
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
    question = activity.questions.first()
    
    if request.user.role != 'STUDENT' or not activity.is_active:
        messages.error(request, "접근할 수 없는 평가입니다.")
        return redirect('dashboard')

    existing_answer = Answer.objects.filter(student__email=request.user.email, question=question).first()
    
    if request.method == 'POST':
        form = AnswerForm(request.POST, instance=existing_answer)
        if form.is_valid():
            answer = form.save(commit=False)
            try:
                answer.student = Student.objects.get(email=request.user.email)
                answer.question = question
                answer.save()
                messages.success(request, "답안이 제출되었습니다!")
                return redirect('dashboard')
            except Student.DoesNotExist:
                messages.error(request, "학생 정보를 찾을 수 없습니다.")
    else:
        form = AnswerForm(instance=existing_answer)

    context = {
        'activity': activity,
        'question': question,
        'form': form,
        'today': timezone.now()
    }
    return render(request, 'activities/take_test.html', context)

# 9. 결시 사유 업데이트 API (AJAX용)
@login_required
@teacher_required
def update_absence(request):
    import json
    from django.http import JsonResponse
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