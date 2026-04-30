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

# 상세 페이지
@login_required
def creative_detail(request, pk):
    activity = get_object_or_404(Activity, pk=pk, teacher=request.user)
    return render(request, 'activities/creative_detail.html', {'activity': activity})


# 7. 제출 현황(답안) 보기 페이지

# 8. 학생 응시 페이지


# 9. 결시 사유 업데이트 API (AJAX용)


# 10. 답안 상세, 삭제, 메모 저장 (추가 필요 시 여기에)






# 학생 활동 로그 저장 API


# 11. 결과 분석 페이지


# 12. 종합 분석 (모든 평가 모아보기)


# 분석 작업 메인 페이지


# DB 답안을 하나씩 AI에게 보내는 로직















# 학생 답안 엑셀 다운로드


# AI 분석 결과 엑셀 다운로드


