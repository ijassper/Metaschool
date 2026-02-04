from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.decorators import teacher_required
from django.contrib import messages
from django.utils import timezone # 날짜 표시용
from django.db.models import Q  # 복합 필터링
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 모델과 폼 가져오기
from .models import Activity, Question, Answer, PromptTemplate
from .forms import ActivityForm, QuestionForm, AnswerForm
from accounts.models import Student

# 1. 내가 만든 평가 목록 보기
@login_required
@teacher_required
def activity_list(request):
    # 최신순으로 정렬해서 가져오기
    activities = Activity.objects.filter(teacher=request.user).order_by('-created_at')
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

# 2. 평가 생성 (과목명 수동 입력 반영)
@login_required
@teacher_required
def create_test(request):
    if request.method == 'POST':
        a_form = ActivityForm(request.POST)
        q_form = QuestionForm(request.POST)
        
        # 선택된 학생 ID 리스트 가져오기
        selected_student_ids = request.POST.getlist('target_students')

        if a_form.is_valid() and q_form.is_valid():
            activity = a_form.save(commit=False)
            activity.teacher = request.user
            activity.save()
            
            # ★ [핵심] 선택된 학생들 연결
            if selected_student_ids:
                activity.target_students.set(selected_student_ids)

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
        
    # ★ 트리 데이터 전달
    student_tree = get_student_tree(request.user)
    
    return render(request, 'activities/create_test.html', {
        'a_form': a_form, 'q_form': q_form, 'action': '생성',
        'student_tree': student_tree # 전달
    })

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
        selected_student_ids = request.POST.getlist('target_students')

        if a_form.is_valid() and q_form.is_valid():
            activity = a_form.save() # M2M 저장을 위해 save() 먼저
            # 대상 업데이트
            activity.target_students.set(selected_student_ids)
            q_form.save()
            
            messages.success(request, "평가가 수정되었습니다.")
            return redirect('activity_list')
    else:
        a_form = ActivityForm(instance=activity)
        q_form = QuestionForm(instance=question)

    student_tree = get_student_tree(request.user)
    # 이미 선택된 학생 ID 리스트 (수정 시 체크 유지용)
    current_targets = list(activity.target_students.values_list('id', flat=True))

    return render(request, 'activities/create_test.html', {
        'a_form': a_form, 'q_form': q_form, 'action': '수정',
        'student_tree': student_tree,
        'current_targets': current_targets
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
    question = activity.questions.first()

    # 1. 학생 권한 및 활성화 체크
    if request.user.role != 'STUDENT' or not activity.is_active:
        messages.error(request, "접근할 수 없는 평가입니다.")
        return redirect('dashboard')

    # 2. 내 정보 가져오기
    try:
        student_info = Student.objects.get(email=request.user.email)
    except Student.DoesNotExist:
        messages.error(request, "학생 정보를 찾을 수 없습니다.")
        return redirect('dashboard')

    # ★ [신규] 3. 내가 대상자가 맞는지 확인 (보안 강화)
    # (선생님이 나를 체크하지 않았는데 주소 알고 들어오는 것 방지)
    if student_info not in activity.target_students.all():
        messages.error(request, "본인의 평가 대상이 아닙니다.")
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
            
            # 현재 시간 (한국 시간)
            now = timezone.localtime()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            
            log_msg = ""
            if action_type == 'OUT':
                log_msg = f"⚠️ [이탈] {timestamp} - 화면을 벗어남\n"
            elif action_type == 'IN':
                log_msg = f"✅ [복귀] {timestamp} - 화면으로 돌아옴\n"
            
            # 로그 누적 저장
            if log_msg:
                answer.activity_log += log_msg
                answer.save()
                
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'fail'})

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
        has_answer = False

        if answer:
            content = answer.content
            submitted_at = answer.submitted_at
            has_answer = True
        
        analysis_list.append({
            'student': student,
            'has_answer': has_answer,
            'content': content,
            'submitted_at': submitted_at,
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

    # activities/views.py

# 분석 작업 메인 페이지
@login_required
@teacher_required
def activity_analysis_work(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    question = activity.questions.first()
    
    # 답안을 제출한 학생들만 가져와서 ID 리스트를 만듦
    answers = Answer.objects.filter(question=question).select_related('student')
    
    # 자바스크립트가 이해할 수 있도록 JSON 명단 생성
    answer_list = []
    for a in answers:
        answer_list.append({
            'id': a.id,
            'name': a.student.name,
            'info': f"{a.student.grade}-{a.student.class_no}-{a.student.number}"
        })

    context = {
        'activity': activity,
        'question': question,
        'submit_count': len(answer_list),
        'answer_list_json': json.dumps(answer_list), # JS로 넘길 명단
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
            answer_id = body.get('answer_id') # 이번엔 index가 아니라 answer의 실제 ID
            prompt_system = body.get('prompt_system')
            temperature = float(body.get('temperature', 0.7))
            ai_model = body.get('ai_model', 'gpt-3.5-turbo')
            
            # 1. 답안 데이터 가져오기
            answer = Answer.objects.get(id=answer_id)
            student = answer.student
            
            # 2. 프롬프트 재료 조합 (학생 정보 + 답안 내용)
            student_info = f"[학생: {student.name}({student.grade}-{student.class_no}-{student.number})]"
            student_answer = f"[학생 답안]\n{answer.content}"
            
            final_prompt = f"{student_info}\n{student_answer}\n\n[지시사항]\n{prompt_system}"
            
            # 3. API 키 가져오기
            config = SystemConfig.objects.get(key_name='OPENAI_API_KEY')
            # (멀티 키 랜덤 선택 로직은 이전과 동일하게 유지)
            api_keys = [k.strip() for k in config.value.split(',') if k.strip()]
            selected_key = random.choice(api_keys)
            
            # 4. AI 호출 (GPT 또는 Gemini 선택 로직)
            # 여기서는 GPT 예시로 작성 (Gemini 로직도 동일하게 추가 가능)
            client = openai.OpenAI(api_key=selected_key)
            response = client.chat.completions.create(
                model=ai_model,
                messages=[
                    {"role": "system", "content": "당신은 학생들의 서술형 답안을 전문적으로 분석하는 교사입니다."},
                    {"role": "user", "content": final_prompt}
                ],
                temperature=temperature
            )
            ai_text = response.choices[0].message.content
            
            # 5. ★ 중요: DB에 분석 결과 즉시 저장 ★
            answer.ai_result = ai_text
            answer.save()
            
            return JsonResponse({'status': 'success', 'result': '저장 완료'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})