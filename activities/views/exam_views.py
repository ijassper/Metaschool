import json
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# 커스텀 데코레이터 및 모델 임포트
from accounts.decorators import teacher_required
from accounts.models import Student, SystemConfig
from ..models import Activity, Question, Answer

LOG_MESSAGES = {
    'IN': '시험 시작',
    'SUBMIT': '답안 제출',
    'RETURN': '답안지 페이지로 재입장',
    'RE_EDIT': '답안 제출 후 수정 위해 재입장',
    'OUT': 'Alt+Tab 또는 창 전환으로 답안지 페이지 이탈',
    'EXIT': '나가기 버튼을 누르고 답안지 페이지 이탈',
    'COPY': '복사 시도',
    'PASTE': '붙여넣기 시도',
    'RIGHT_CLICK': '우클릭 시도',
    'BACK_BUTTON': '브라우저 뒤로가기 버튼 클릭 시도',
}


def append_activity_log(answer, action_code, timestamp=None):
    if timestamp is None:
        now = timezone.localtime(timezone.now())
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    message = LOG_MESSAGES.get(action_code, action_code)
    answer.activity_log = (answer.activity_log or "") + f"[{timestamp}] {message}\n"


def log_event(action_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, activity_id, *args, **kwargs):
            response = view_func(request, activity_id, *args, **kwargs)
            answer = getattr(request, '_exam_log_answer', None)
            if answer is not None:
                append_activity_log(answer, action_name)
                answer.save(update_fields=['activity_log'])
            return response
        return wrapped
    return decorator


def get_student_for_activity(request, activity):
    if request.user.role != 'STUDENT':
        messages.error(request, "접근할 수 없는 평가입니다.")
        return None, redirect('dashboard')

    student_info = Student.objects.filter(email=request.user.email).first()
    if not student_info:
        messages.error(request, "학생 정보를 찾을 수 없습니다.")
        return None, redirect('dashboard')

    if student_info not in activity.target_students.all():
        messages.error(request, "본인 대상 평가가 아닙니다.")
        return None, redirect('dashboard')

    return student_info, None


def ensure_exam_question(activity):
    question, _ = Question.objects.get_or_create(
        activity=activity,
        defaults={
            'content': activity.question,
            'conditions': activity.conditions,
            'reference': activity.reference_material,
        }
    )
    return question


def build_exam_context(request, activity, question, answer=None, exam_started=False):
    try:
        demo_config = SystemConfig.objects.get(key_name='IS_DEMO_MODE')
        is_demo = demo_config.value.strip().upper() == 'Y'
    except SystemConfig.DoesNotExist:
        is_demo = False

    security_state = update_exam_security_session(request, activity)
    is_copy_locked = security_state['is_copy_protected']
    exam_mode = activity.exam_mode
    is_closed_mode = exam_mode.startswith('CLOSED_') or exam_mode == 'CLOSED'
    enable_exit_detection = is_closed_mode and not is_demo
    enable_copy_protection = is_copy_locked and not is_demo

    return {
        'activity': activity,
        'question': question,
        'answer': answer,
        'answer_id': answer.id if answer else '',
        'exam_started': exam_started,
        'entry_action_url': 're_enter_exam' if answer and answer.submitted_at else 'start_exam',
        'exam_mode': exam_mode,
        'is_closed_mode': is_closed_mode,
        'is_copy_locked': is_copy_locked,
        'IS_COPY_PROTECTED': is_copy_locked,
        'enable_exit_detection': enable_exit_detection,
        'enable_copy_protection': enable_copy_protection,
        'is_demo': is_demo,
    }

def save_answer_content(answer, activity, form_data):
    answer.ans_q1 = form_data.get('ans_q1', '').strip()
    answer.ans_q2 = form_data.get('ans_q2', '').strip()
    answer.ans_q3 = form_data.get('ans_q3', '').strip()

    if any([answer.ans_q1, answer.ans_q2, answer.ans_q3]):
        answer.content = (
            f"[{activity.q1_title}]\n{answer.ans_q1}\n\n"
            f"[{activity.q2_title}]\n{answer.ans_q2}\n\n"
            f"[{activity.q3_title}]\n{answer.ans_q3}"
        )
    else:
        answer.content = ""


def update_exam_security_session(request, activity):
    """DB의 응시 환경을 현재 학생 세션의 보안 상태로 동기화합니다."""
    security_state = {
        'activity_id': activity.id,
        'exam_mode': activity.exam_mode,
        'is_copy_protected': activity.is_copy_protected,
    }
    request.session['exam_security'] = security_state
    request.session.modified = True
    return security_state

# [1] Student exam/pre-entry page
@login_required
def take_test(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id)

    student_info, error_response = get_student_for_activity(request, activity)
    if error_response:
        return error_response

    existing_answer = Answer.objects.filter(student=student_info, question__activity=activity).first()
    if existing_answer and existing_answer.submitted_at and not activity.allow_edit_after_submission:
        messages.warning(request, "제출 완료된 평가 활동은 재입장할 수 없습니다")
        return redirect('dashboard')

    if not activity.is_attainable:
        messages.warning(request, "현재 응시할 수 없는 평가 활동입니다")
        return redirect('dashboard')

    question = ensure_exam_question(activity)
    answer = existing_answer

    if request.method == 'POST':
        answer, _ = Answer.objects.get_or_create(student=student_info, question=question)
        is_exit_submit = request.POST.get('is_exit') == 'true'
        is_final_submit = request.POST.get('is_submit') == 'true' or is_exit_submit

        save_answer_content(answer, activity, request.POST)

        if is_final_submit:
            now = timezone.localtime(timezone.now())
            answer.submitted_at = now
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            if is_exit_submit:
                append_activity_log(answer, 'EXIT', timestamp)
            else:
                append_activity_log(answer, 'SUBMIT', timestamp)

        answer.save()

        if is_final_submit:
            messages.success(request, "답안이 제출되었습니다")
            return redirect('dashboard')
        return JsonResponse({'status': 'success', 'message': '임시 저장 완료'})

    context = build_exam_context(request, activity, question, answer=answer, exam_started=False)
    return render(request, 'activities/take_test.html', context)


@require_POST
@login_required
def save_answer_draft(request, activity_id):
    """Save student work without navigation or activity-log side effects."""
    activity = get_object_or_404(Activity, id=activity_id)
    student_info, error_response = get_student_for_activity(request, activity)
    if error_response:
        return JsonResponse({'status': 'error', 'message': '저장 권한이 없습니다.'}, status=403)
    if not activity.is_attainable:
        return JsonResponse({'status': 'error', 'message': '현재 임시 저장할 수 없습니다.'}, status=403)

    question = ensure_exam_question(activity)
    answer, _ = Answer.objects.get_or_create(student=student_info, question=question)
    if answer.submitted_at and not activity.allow_edit_after_submission:
        return JsonResponse({'status': 'error', 'message': '제출이 완료되어 수정할 수 없습니다.'}, status=403)

    save_answer_content(answer, activity, request.POST)
    answer.save(update_fields=['ans_q1', 'ans_q2', 'ans_q3', 'content'])

    return JsonResponse({
        'status': 'success',
        'message': '임시저장이 완료되었습니다.',
        'answer_id': answer.id,
    })


@require_POST
@login_required
@log_event("시험 시작")
def start_exam(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id)
    student_info, error_response = get_student_for_activity(request, activity)
    if error_response:
        return JsonResponse({'status': 'error', 'message': 'forbidden'}, status=403)
    if not activity.is_attainable:
        return JsonResponse({'status': 'error', 'message': 'unavailable'}, status=403)

    question = ensure_exam_question(activity)
    answer, _ = Answer.objects.get_or_create(student=student_info, question=question)
    request._exam_log_answer = answer
    return JsonResponse({'status': 'success', 'answer_id': answer.id})


@require_POST
@login_required
@log_event("답안 제출 후 수정 위해 재입장")
def re_enter_exam(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id)
    student_info, error_response = get_student_for_activity(request, activity)
    if error_response:
        return JsonResponse({'status': 'error', 'message': 'forbidden'}, status=403)
    if not activity.is_attainable or not activity.allow_edit_after_submission:
        return JsonResponse({'status': 'error', 'message': 'unavailable'}, status=403)

    question = ensure_exam_question(activity)
    answer = Answer.objects.filter(student=student_info, question=question, submitted_at__isnull=False).first()
    if not answer:
        return JsonResponse({'status': 'error', 'message': 'submitted answer not found'}, status=404)

    request._exam_log_answer = answer
    return JsonResponse({'status': 'success', 'answer_id': answer.id})

# [2] Security and activity log API
@login_required
def log_activity(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            answer_id = data.get('answer_id')
            action_type = data.get('type') # 'OUT'(이탈) 또는 'IN'(복귀)
            log_type = data.get('type') # 'OUT'(?댄깉) ?먮뒗 'IN'(蹂듦?)
            allowed_log_types = {'OUT', 'EXIT', 'COPY', 'PASTE', 'RIGHT_CLICK', 'BACK_BUTTON'}
            if log_type not in allowed_log_types:
                return JsonResponse({'status': 'ignored'})
            
            answer = Answer.objects.get(id=answer_id)
            
            # 기존 로그에 새로운 기록 추가 (줄바꿈 포함)
            current_log = answer.activity_log if answer.activity_log else ""
            now = timezone.localtime(timezone.now())
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            
            answer.activity_log = current_log
            append_activity_log(answer, log_type, timestamp)
            if log_type in ['OUT', 'EXIT', 'BACK_BUTTON'] and not answer.submitted_at:
                answer.submitted_at = now
                answer.save(update_fields=['activity_log', 'submitted_at'])
            else:
                answer.save(update_fields=['activity_log'])
            
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
