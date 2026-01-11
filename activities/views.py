from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.decorators import teacher_required
from accounts.models import Student
from .models import Activity, Question, Answer
from .forms import ActivityForm, QuestionForm, AnswerForm
from django.contrib import messages
from django.utils import timezone # 날짜 표시용

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
    
    # 학년/반 목록 추출 (중복 제거)
    grade_list = all_students.values_list('grade', flat=True).distinct().order_by('grade')
    class_list = all_students.values_list('class_no', flat=True).distinct().order_by('class_no')

    # 2. 검색 조건 가져오기
    current_grade = request.GET.get('grade')
    current_class = request.GET.get('class_no')
    name_query = request.GET.get('q')

    # 3. [핵심] 초기 진입 시 기본값 설정 (1학년 1반 등 가장 첫 번째 반으로 설정)
    # 검색어(이름)가 없을 때만 기본값을 적용합니다. (이름 검색 시에는 전체에서 찾아야 하니까요)
    if not current_grade and not current_class and not name_query:
        if grade_list.exists() and class_list.exists():
            current_grade = grade_list[0] # 가장 낮은 학년
            current_class = class_list[0] # 가장 앞 반

    # 4. 실제 보여줄 학생 필터링
    target_students = all_students

    if current_grade:
        target_students = target_students.filter(grade=current_grade)
    if current_class:
        target_students = target_students.filter(class_no=current_class)
    if name_query:
        # 이름 검색 시에는 학년/반 필터를 무시하고 전체에서 찾을지, 
        # 아니면 선택된 반 안에서 찾을지 결정해야 합니다.
        # 보통 이름 검색은 전체에서 찾는 게 편하므로, 이름이 있으면 학년/반 필터가 있어도 추가로 검색합니다.
        # 여기서는 '선택된 학년/반 내에서 이름 검색'으로 구현합니다. (가장 빠름)
        target_students = target_students.filter(name__contains=name_query)

    # 5. 제출 현황 매칭
    submission_list = []
    question = activity.questions.first()

    for student in target_students:
        answer = Answer.objects.filter(student=student, question=question).first()
        
        status = "미응시"
        submitted_at = "-"
        answer_id = None
        note = ""

        if answer:
            status = "제출 완료"
            submitted_at = answer.submitted_at
            answer_id = answer.id
            note = answer.note

        submission_list.append({
            'student': student,
            'status': status,
            'submitted_at': submitted_at,
            'answer_id': answer_id,
            'note': note
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