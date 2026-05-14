import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 커스텀 데코레이터 및 모델 임포트
from accounts.decorators import teacher_required
from accounts.models import Student, SystemConfig
from ..models import Activity, Question, Answer

# [1] 학생 응시 페이지
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

    # 4. [신규] 제출 후 수정 제한 및 기한 체크
    # (1) 제출 기한이 지났는지 확인
    if activity.deadline and timezone.now() > activity.deadline:
        messages.error(request, "제출 기한이 종료되었습니다. 더 이상 수정할 수 없습니다.")
        return redirect('dashboard')

    # (2) 제출 후 수정 불가 설정인데 이미 제출했는지 확인
    # Answer 객체를 미리 조회하여 제출 여부 파악
    existing_answer = Answer.objects.filter(student=student_info, question__activity=activity).first()
    if not activity.allow_edit_after_submission and existing_answer and existing_answer.submitted_at:
        messages.error(request, "답안이 이미 제출되었습니다. 제출된 답안은 수정이 불가합니다.")
        return redirect('dashboard')

    # [추가] 데모 모드 설정값 가져오기
    try:
        demo_config = SystemConfig.objects.get(key_name='IS_DEMO_MODE')
        is_demo = demo_config.value.strip().upper() == 'Y'
    except SystemConfig.DoesNotExist:
        is_demo = False

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
        'question': question,  # [추가] 템플릿에서 문항 정보를 쉽게 쓰기 위해
        'answer': answer,
        'answer_id': answer.id,
        'is_demo': is_demo,    # [추가] 시연 모드 여부 전달 (복붙 허용 로직용)
    })

# [2] 보안 및 활동 로그 저장 API
@login_required
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

# [3] 결시 사유 업데이트 API
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