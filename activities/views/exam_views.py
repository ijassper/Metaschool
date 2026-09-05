import json
import hashlib
from functools import wraps
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

# 커스텀 데코레이터 및 모델 임포트
from accounts.decorators import teacher_required
from accounts.models import Student, SystemConfig
from ..models import (
    Activity, Question, Answer, AnswerDraftRevision, ActivityStudentScore, FeedbackResult,
)

LOG_MESSAGES = {
    'IN': '답안지 페이지 입장',
    'SUBMIT': '답안 제출',
    'RETURN': '답안지 페이지 입장',
    'RE_EDIT': '답안지 페이지 입장',
    'OUT': 'Alt+Tab 또는 창 전환으로 답안지 페이지 이탈',
    'EXIT': '나가기 버튼을 누르고 답안지 페이지 이탈',
    'COPY': '복사 시도',
    'PASTE': '붙여넣기 시도',
    'RIGHT_CLICK': '우클릭 시도',
    'BACK_BUTTON': '브라우저 뒤로가기 버튼 클릭 시도',
}

MAX_NOTEBOOK_PAGES = 100
MAX_NOTEBOOK_PAGE_CHARS = 20000
MAX_DRAFT_REVISIONS = 10
DRAFT_REVISION_MIN_INTERVAL_SECONDS = 60


def normalize_notebook_pages(raw_pages, legacy_content=''):
    """Return a safe list of notebook page strings, preserving legacy notes."""
    if isinstance(raw_pages, str):
        try:
            raw_pages = json.loads(raw_pages)
        except (TypeError, ValueError, json.JSONDecodeError):
            raw_pages = None

    if not isinstance(raw_pages, list):
        raw_pages = [legacy_content or '']

    pages = [str(page or '')[:MAX_NOTEBOOK_PAGE_CHARS] for page in raw_pages[:MAX_NOTEBOOK_PAGES]]
    non_empty_pages = [page for page in pages if page.strip()]
    return non_empty_pages or ['']


def build_answer_snapshot(answer):
    notebook_pages = list(answer.notebook_pages or [])
    return {
        'ans_q1': '' if notebook_pages else (answer.ans_q1 or ''),
        'ans_q2': '' if notebook_pages else (answer.ans_q2 or ''),
        'ans_q3': '' if notebook_pages else (answer.ans_q3 or ''),
        'notebook_pages': notebook_pages,
    }


def snapshot_char_count(snapshot):
    notebook_pages = snapshot.get('notebook_pages') or []
    values = notebook_pages or [
        snapshot.get('ans_q1', ''), snapshot.get('ans_q2', ''), snapshot.get('ans_q3', '')
    ]
    return sum(len(''.join(str(value or '').split())) for value in values)


def snapshot_fingerprint(snapshot):
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def preserve_answer_revision(answer, new_snapshot, requested_reason='PERIODIC'):
    """기존 답안을 필요할 때만 보관해 자동저장 요청 수와 이력 증가를 제한합니다."""
    old_snapshot = build_answer_snapshot(answer)
    old_count = snapshot_char_count(old_snapshot)
    new_count = snapshot_char_count(new_snapshot)
    if old_count == 0 or snapshot_fingerprint(old_snapshot) == snapshot_fingerprint(new_snapshot):
        return None

    is_destructive = old_count >= 100 and new_count <= old_count * 0.5
    last_revision = answer.draft_revisions.order_by('-created_at', '-id').first()
    interval_elapsed = (
        last_revision is None
        or (timezone.now() - last_revision.created_at).total_seconds() >= DRAFT_REVISION_MIN_INTERVAL_SECONDS
    )
    valid_reasons = {value for value, _ in AnswerDraftRevision.SaveReason.choices}
    reason = requested_reason if requested_reason in valid_reasons else AnswerDraftRevision.SaveReason.PERIODIC
    if is_destructive:
        reason = AnswerDraftRevision.SaveReason.DESTRUCTIVE_EDIT
    elif not interval_elapsed and reason != AnswerDraftRevision.SaveReason.MANUAL:
        return None

    fingerprint = snapshot_fingerprint(old_snapshot)
    if last_revision and last_revision.fingerprint == fingerprint:
        return None

    revision = AnswerDraftRevision.objects.create(
        answer=answer,
        content_snapshot=old_snapshot,
        char_count=old_count,
        fingerprint=fingerprint,
        save_reason=reason,
    )
    stale_ids = list(
        answer.draft_revisions.order_by('-created_at', '-id')
        .values_list('id', flat=True)[MAX_DRAFT_REVISIONS:]
    )
    if stale_ids:
        AnswerDraftRevision.objects.filter(id__in=stale_ids).delete()
    return revision


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

    if not activity.target_students.filter(pk=student_info.pk).exists():
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


def build_exam_context(request, activity, question, answer=None, exam_started=False, student=None):
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

    notebook_pages = []
    if activity.is_notebook:
        notebook_pages = normalize_notebook_pages(
            answer.notebook_pages if answer else None,
            answer.ans_q1 if answer else '',
        )

    return {
        'activity': activity,
        'question': question,
        'answer': answer,
        'student': student or (answer.student if answer else None),
        'notebook_pages': notebook_pages,
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


@login_required
def pdf_viewer(request):
    """Render a same-origin PDF inside the in-page PDF.js viewer."""
    file_url = request.GET.get('file', '').strip()
    parsed_url = urlparse(file_url)
    allowed_prefixes = (
        settings.MEDIA_URL,
        f"/{settings.STATIC_URL.lstrip('/')}",
    )

    if (
        not file_url
        or parsed_url.scheme
        or parsed_url.netloc
        or '..' in parsed_url.path.split('/')
        or not parsed_url.path.lower().endswith('.pdf')
        or not parsed_url.path.startswith(allowed_prefixes)
    ):
        return render(
            request,
            'activities/pdf_viewer.html',
            {'pdf_file_url': '', 'viewer_error': '올바른 PDF 파일 경로가 아닙니다.'},
            status=400,
        )

    return render(
        request,
        'activities/pdf_viewer.html',
        {'pdf_file_url': file_url, 'viewer_error': ''},
    )


def save_answer_content(answer, activity, form_data):
    answer.ans_q1 = form_data.get('ans_q1', '').strip()
    answer.ans_q2 = form_data.get('ans_q2', '').strip()
    answer.ans_q3 = form_data.get('ans_q3', '').strip()

    if activity.is_notebook:
        pages = normalize_notebook_pages(form_data.get('notebook_pages'), answer.ans_q1)
        answer.notebook_pages = pages
        answer.ans_q1 = '\n\n'.join(page.strip() for page in pages if page.strip())
        answer.content = answer.ans_q1
    elif any([answer.ans_q1, answer.ans_q2, answer.ans_q3]):
        answer.content = (
            f"[{activity.q1_title}]\n{answer.ans_q1}\n\n"
            f"[{activity.q2_title}]\n{answer.ans_q2}\n\n"
            f"[{activity.q3_title}]\n{answer.ans_q3}"
        )
    else:
        answer.content = ""


def submitted_answer_char_count(activity, form_data):
    """저장되는 답안 본문과 같은 범위로 전체 글자 수를 계산합니다."""
    if activity.is_notebook:
        pages = normalize_notebook_pages(form_data.get('notebook_pages'), form_data.get('ans_q1', ''))
        return sum(len(page) for page in pages)
    return sum(len(str(form_data.get(name, '') or '')) for name in ('ans_q1', 'ans_q2', 'ans_q3'))


def character_limit_error(activity, current_length):
    if activity.limit_type == 'MAX' and activity.limit_count and current_length > activity.limit_count:
        return f'글자 수가 초과되었습니다. 최대 {activity.limit_count}자 이내로 작성해주세요.'
    if activity.limit_type == 'MIN' and activity.limit_count and current_length < activity.limit_count:
        return f'최소 {activity.limit_count}자 이상 작성해야 제출이 가능합니다.'
    return ''


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

        if is_final_submit:
            limit_error = character_limit_error(activity, submitted_answer_char_count(activity, request.POST))
            if limit_error:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': limit_error}, status=400)
                save_answer_content(answer, activity, request.POST)
                messages.error(request, limit_error)
                context = build_exam_context(
                    request, activity, question, answer=answer, exam_started=True, student=student_info
                )
                return render(request, 'activities/take_test.html', context, status=400)

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

    context = build_exam_context(
        request, activity, question, answer=answer, exam_started=False, student=student_info
    )
    return render(request, 'activities/take_test.html', context)


@login_required
def student_result_detail(request, activity_id):
    """학생 본인에게 응시 내용, 답안, 점수와 교사가 확정한 피드백을 보여줍니다."""
    activity = get_object_or_404(Activity.objects.select_related('teacher'), id=activity_id)
    student_info, error_response = get_student_for_activity(request, activity)
    if error_response:
        return error_response

    answer = (
        Answer.objects.select_related('question', 'student')
        .filter(student=student_info, question__activity=activity)
        .first()
    )
    question = activity.questions.first()
    feedback_results = []
    notebook_pages = []
    if answer:
        feedback_queryset = FeedbackResult.objects.filter(
                answer=answer,
                activity=activity,
                student=student_info,
                is_published=True,
            ).order_by('-created_at', '-id')
        feedback_results = list(feedback_queryset)
        unread_ids = [feedback.id for feedback in feedback_results if not feedback.is_read]
        if unread_ids:
            first_read_at = timezone.now()
            FeedbackResult.objects.filter(id__in=unread_ids, is_read=False).update(
                is_read=True,
                read_at=first_read_at,
            )
            for feedback in feedback_results:
                if feedback.id in unread_ids:
                    feedback.is_read = True
                    feedback.read_at = first_read_at
        if activity.is_notebook:
            notebook_pages = normalize_notebook_pages(answer.notebook_pages, answer.ans_q1)
    stored_score = ActivityStudentScore.objects.filter(
        activity=activity,
        student=student_info,
    ).values_list('score', flat=True).first()
    display_score = (
        stored_score
        if stored_score is not None
        else (answer.score if answer and answer.score is not None else 0)
    )

    return render(request, 'activities/student_result_detail.html', {
        'activity': activity,
        'question': question,
        'answer': answer,
        'student': student_info,
        'score': display_score,
        'feedback_results': feedback_results,
        'notebook_pages': notebook_pages,
    })


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

    new_notebook_pages = (
        normalize_notebook_pages(
            request.POST.get('notebook_pages'),
            request.POST.get('ans_q1', ''),
        ) if activity.is_notebook else []
    )
    new_snapshot = {
        'ans_q1': '' if new_notebook_pages else request.POST.get('ans_q1', '').strip(),
        'ans_q2': '' if new_notebook_pages else request.POST.get('ans_q2', '').strip(),
        'ans_q3': '' if new_notebook_pages else request.POST.get('ans_q3', '').strip(),
        'notebook_pages': new_notebook_pages,
    }
    preserve_answer_revision(
        answer,
        new_snapshot,
        request.POST.get('draft_save_reason', AnswerDraftRevision.SaveReason.PERIODIC),
    )
    save_answer_content(answer, activity, request.POST)
    answer.updated_at = timezone.now()
    answer.save(update_fields=['ans_q1', 'ans_q2', 'ans_q3', 'notebook_pages', 'content', 'updated_at'])

    return JsonResponse({
        'status': 'success',
        'message': '임시저장이 완료되었습니다.',
        'answer_id': answer.id,
    })


@require_GET
@login_required
def draft_revision_list(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id)
    student_info, error_response = get_student_for_activity(request, activity)
    if error_response:
        return JsonResponse({'status': 'error', 'message': '조회 권한이 없습니다.'}, status=403)
    answer = Answer.objects.filter(student=student_info, question__activity=activity).first()
    if not answer:
        return JsonResponse({'status': 'success', 'revisions': []})
    revisions = list(
        answer.draft_revisions.order_by('-created_at', '-id')[:MAX_DRAFT_REVISIONS]
    )
    return JsonResponse({
        'status': 'success',
        'revisions': [
            {
                'id': revision.id,
                'created_at': revision.created_at.isoformat(),
                'char_count': revision.char_count,
                'reason': revision.save_reason,
            }
            for revision in revisions
        ],
    })


@require_GET
@login_required
def draft_revision_detail(request, activity_id, revision_id):
    activity = get_object_or_404(Activity, id=activity_id)
    student_info, error_response = get_student_for_activity(request, activity)
    if error_response:
        return JsonResponse({'status': 'error', 'message': '조회 권한이 없습니다.'}, status=403)
    revision = get_object_or_404(
        AnswerDraftRevision.objects.select_related('answer', 'answer__question'),
        id=revision_id,
        answer__student=student_info,
        answer__question__activity=activity,
    )
    return JsonResponse({
        'status': 'success',
        'revision': {
            'id': revision.id,
            'created_at': revision.created_at.isoformat(),
            'char_count': revision.char_count,
            'snapshot': revision.content_snapshot,
        },
    })


@require_POST
@login_required
@log_event("답안지 페이지 입장")
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
@log_event("답안지 페이지 입장")
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
