# 제출 현황 및 답안 관리 (activity_result, answer_detail 등)

import json
import re
from urllib.parse import urlencode
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

# 커스텀 데코레이터 및 모델 임포트
from accounts.decorators import teacher_required
from accounts.models import Persona, Student
from ..models import Activity, Answer, FeedbackResult, FeedbackSession
from .main_views import get_accessible_students


def parse_quick_score(value):
    if isinstance(value, bool):
        raise ValueError('invalid score')
    score = int(value)
    if score < 0 or score > 5:
        raise ValueError('invalid score')
    return score

# [1] 제출 현황(답안) 목록 페이지
@login_required
@teacher_required
def activity_result(request, activity_id, template_name='activities/activity_result.html'):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    
    # 1. [항상 실행] 필터 메뉴 구성을 위한 '전체 대상 학생' 가져오기
    all_students_for_filter = activity.target_students.all().order_by('grade', 'class_no', 'number')
    if not all_students_for_filter.exists():
        all_students_for_filter = get_accessible_students(request.user)

    # 2. [항상 실행] filter_data 변수 초기화 및 생성
    # 이 부분이 if문 밖에 있어야 NameError가 나지 않습니다.
    temp_data = {}
    for s in all_students_for_filter:
        g = s.grade
        c = s.class_no
        if g not in temp_data: temp_data[g] = []
        if c not in temp_data[g]: temp_data[g].append(c)
    
    filter_data = [] # 여기서 변수가 확실히 생성됩니다.
    for g in sorted(temp_data.keys()):
        filter_data.append({
            'grade': g,
            'classes': sorted(list(set(temp_data[g])))
        })

    # 3. 검색 조건 처리
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')
    show_all = request.GET.get('show_all') == '1'

    # 4. [선택적 실행] 목록 데이터 필터링
    if not selected_targets and not name_query and not show_all:
        target_students = Student.objects.none() # 최초 진입 시 데이터 없음
    else:
        target_students = all_students_for_filter
        if selected_targets:
            q_objects = Q()
            for t in selected_targets:
                if '_' in t:
                    g, c = t.split('_')
                    q_objects |= Q(grade=g, class_no=c)
            target_students = target_students.filter(q_objects)

        if name_query:
            target_students = target_students.filter(name__contains=name_query)

    # 6. 제출 현황 정리
    submission_list = []
    question = activity.questions.first()
    is_deadline_passed = bool(activity.deadline and timezone.now() > activity.deadline)

    for student in target_students:
        answer = Answer.objects.filter(
            student=student,
            question=question,
        ).select_related('question__activity').first()
        status = "미응시"
        submitted_at = "-"
        answer_id = None
        content = ""  # [추가] 답안 내용을 담을 변수
        note = ""
        absence = ""

        log_data = ""
        if answer:
            answer_id = answer.id
            note = answer.note
            absence = answer.absence_type
            log_data = answer.activity_log 
            content = answer.display_content
            
            structured_text = " ".join([
                answer.ans_q1 or "",
                answer.ans_q2 or "",
                answer.ans_q3 or "",
            ])
            fallback_text = re.sub(r'^\s*\[.*?\]\s*$', '', answer.content or "", flags=re.MULTILINE)
            answer_text = structured_text if structured_text.strip() else fallback_text
            has_content = bool(answer_text.strip())

            if absence:
                status = "결시"
            elif answer.submitted_at and not has_content:
                status = "백지 제출"
                submitted_at = answer.submitted_at
            elif answer.submitted_at:
                status = "제출 완료"
                submitted_at = answer.submitted_at
            elif is_deadline_passed and not has_content:
                status = "백지 제출"
            else:
                status = "응시 중"
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
            'content': content, # [핵심 추가] 리스트에 담아서 템플릿으로 전달
            'score': answer.score if answer else None,
        })

    context = {
        'activity': activity,
        'submission_list': submission_list,
        'filter_data': filter_data,
        'selected_targets': selected_targets,
        'current_q': name_query,
        'personas': Persona.objects.filter(
            Q(creator__isnull=True) | Q(creator=request.user)
        ).select_related('creator'),
    }
    return render(request, template_name, context)

# [2] 답안 상세 페이지
@login_required
@teacher_required
def answer_detail(request, answer_id):
    answer = get_object_or_404(
        Answer.objects.select_related(
            'student',
            'student__school',
            'question',
            'question__activity',
        ),
        id=answer_id,
        question__activity__teacher=request.user,
    )
    feedback_sessions = answer.feedback_sessions.filter(
        created_by=request.user
    ).order_by('-version', '-id')
    ordered_answer_ids = list(
        Answer.objects.filter(
            question__activity=answer.question.activity,
            question__activity__teacher=request.user,
            submitted_at__isnull=False,
        )
        .order_by('student__grade', 'student__class_no', 'student__number', 'student__name', 'id')
        .values_list('id', flat=True)
    )
    next_answer_id = None
    if answer.id in ordered_answer_ids:
        current_index = ordered_answer_ids.index(answer.id)
        if current_index + 1 < len(ordered_answer_ids):
            next_answer_id = ordered_answer_ids[current_index + 1]
    return render(request, 'activities/answer_detail.html', {
        'answer': answer,
        'activity': answer.question.activity,
        'feedback_logs': answer.feedback_results.all(),
        'feedback_sessions': feedback_sessions,
        'next_answer_id': next_answer_id,
        'personas': Persona.objects.filter(
            Q(creator__isnull=True) | Q(creator=request.user)
        ).select_related('creator'),
    })


@require_POST
@login_required
@teacher_required
def update_answer_score(request, answer_id):
    answer = get_object_or_404(
        Answer.objects.select_related('question__activity'),
        id=answer_id,
        question__activity__teacher=request.user,
    )
    try:
        payload = json.loads(request.body or '{}')
        score = parse_quick_score(payload.get('score'))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse(
            {'status': 'error', 'message': '점수는 0점부터 5점까지만 선택할 수 있습니다.'},
            status=400,
        )

    answer.score = score
    answer.save(update_fields=['score'])
    return JsonResponse({'status': 'success', 'score': score, 'label': f'{score}점'})


@require_POST
@login_required
@teacher_required
def save_feedback_result(request, answer_id):
    answer = get_object_or_404(
        Answer.objects.select_related('student', 'question__activity'),
        id=answer_id,
        question__activity__teacher=request.user,
    )
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': '저장 요청 형식이 올바르지 않습니다.'}, status=400)

    feedback_content = str(payload.get('feedback_content') or '').strip()
    task_type = str(payload.get('task_type') or '').strip()
    persona_used = payload.get('persona_used') or {}
    feedback_session_id = payload.get('feedback_session_id')
    feedback_title = str(payload.get('feedback_title') or '').strip()[:150]
    options_snapshot = payload.get('options_snapshot')
    if not isinstance(options_snapshot, dict):
        options_snapshot = persona_used
    valid_task_types = {value for value, _ in FeedbackResult.TaskType.choices}
    if not feedback_content:
        return JsonResponse({'status': 'error', 'message': '저장할 결과 내용을 입력해주세요.'}, status=400)
    if not feedback_title:
        return JsonResponse({'status': 'error', 'message': '생성 결과 제목을 입력해주세요.'}, status=400)
    if task_type not in valid_task_types:
        return JsonResponse({'status': 'error', 'message': '지원하지 않는 작업 유형입니다.'}, status=400)
    if not isinstance(persona_used, dict):
        persona_used = {'summary': str(persona_used)[:500]}

    feedback_session = None
    if feedback_session_id:
        feedback_session = FeedbackSession.objects.filter(
            id=feedback_session_id,
            answer=answer,
            created_by=request.user,
        ).first()
        if not feedback_session:
            return JsonResponse({'status': 'error', 'message': '저장할 작업 버전을 찾을 수 없습니다.'}, status=404)
        feedback_title = FeedbackSession.make_unique_title(
            answer=answer,
            created_by=request.user,
            title=feedback_title,
            exclude_session_id=feedback_session.id,
        )

    feedback = FeedbackResult.objects.create(
        student=answer.student,
        activity=answer.question.activity,
        answer=answer,
        task_type=task_type,
        feedback_title=feedback_title,
        feedback_content=feedback_content,
        persona_used=persona_used,
    )
    if feedback_session:
        session_updates = {
            'content': feedback_content,
            'options_snapshot': options_snapshot,
            'status': FeedbackSession.Status.FINAL,
            'updated_at': timezone.now(),
        }
        if feedback_title:
            session_updates['feedback_title'] = feedback_title
        FeedbackSession.objects.filter(id=feedback_session.id).update(**session_updates)
    return JsonResponse({
        'status': 'success',
        'feedback_id': feedback.id,
        'type_name': feedback.type_name,
        'feedback_title': feedback.display_title,
    })


def _serialize_feedback_session(session):
    return {
        'id': session.id,
        'feedback_title': session.feedback_title,
        'content': session.content,
        'options_snapshot': session.options_snapshot,
        'version': session.version,
        'status': session.status,
        'status_label': session.get_status_display(),
        'created_at': timezone.localtime(session.created_at).strftime('%Y.%m.%d %H:%M'),
        'updated_at': timezone.localtime(session.updated_at).strftime('%Y.%m.%d %H:%M'),
    }


@require_GET
@login_required
@teacher_required
def feedback_session_detail(request, answer_id, session_id):
    session = get_object_or_404(
        FeedbackSession.objects.select_related('answer__question__activity'),
        id=session_id,
        answer_id=answer_id,
        answer__question__activity__teacher=request.user,
        created_by=request.user,
    )
    return JsonResponse({'status': 'success', 'session': _serialize_feedback_session(session)})


@require_POST
@login_required
@teacher_required
def save_feedback_session(request, answer_id, session_id):
    session = get_object_or_404(
        FeedbackSession.objects.select_related('answer__question__activity'),
        id=session_id,
        answer_id=answer_id,
        answer__question__activity__teacher=request.user,
        created_by=request.user,
    )
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': '저장 요청 형식이 올바르지 않습니다.'}, status=400)

    title = str(payload.get('feedback_title') or '').strip()[:150]
    content = str(payload.get('content') or '')
    options_snapshot = payload.get('options_snapshot')
    if options_snapshot is not None and not isinstance(options_snapshot, dict):
        return JsonResponse({'status': 'error', 'message': '생성 옵션 형식이 올바르지 않습니다.'}, status=400)
    if not title:
        return JsonResponse({'status': 'error', 'message': '생성 결과 제목을 입력해주세요.'}, status=400)

    title = FeedbackSession.make_unique_title(
        answer=session.answer,
        created_by=request.user,
        title=title,
        exclude_session_id=session.id,
    )

    session.feedback_title = title
    session.content = content
    session.status = FeedbackSession.Status.DRAFT
    update_fields = ['feedback_title', 'content', 'status', 'updated_at']
    if options_snapshot is not None:
        session.options_snapshot = options_snapshot
        update_fields.append('options_snapshot')
    session.save(update_fields=update_fields)
    return JsonResponse({'status': 'success', 'session': _serialize_feedback_session(session)})

# [3] 답안 삭제(폐기) 처리
@login_required
@teacher_required
def answer_delete(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id)
    activity = answer.question.activity
    activity_id = activity.id
    
    # 답안 삭제
    answer.delete()
    
    messages.success(request, "답안을 삭제(반려)했습니다.")
    
    # 1. Query Parameter (현재 파라미터 보존)
    # category, sub, class_id, target(학급 필터), q(검색어) 등 모든 필수 상태값 추출
    params = {}
    for key in ['category', 'sub', 'class_id', 'q']:
        val = request.GET.get(key)
        if val:
            params[key] = val
            
    # target은 multi-value 파라미터이므로 getlist로 별도 처리
    targets = request.GET.getlist('target')
    if targets:
        params['target'] = targets
        
    if params:
        # urlencode에 doseq=True를 주어 리스트 타입인 target이 올바르게 인코딩되도록 합니다.
        query_string = urlencode(params, doseq=True)
        base_url = reverse('activity_result', kwargs={'activity_id': activity_id})
        return redirect(f'{base_url}?{query_string}')
        
    # 2. Referer (이전 페이지)
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
        
    # 3. 대시보드 메인
    return redirect('dashboard')

# [4] 선생님 특이사항 메모 저장 (AJAX)
@login_required
@teacher_required
def save_note(request, activity_id, student_id):
    if request.method == 'POST':
        try:
            activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
            student = get_object_or_404(get_accessible_students(request.user), id=student_id)
            
            # Answer 객체 조회 또는 생성 (메모 저장을 위해)
            from ..models import Question
            question = activity.questions.first()
            if not question:
                # Question이 없으면 생성 (생성 시점에 이미 생성되어 있어야 함)
                question = Question.objects.create(
                    activity=activity,
                    content=activity.question,
                    conditions=activity.conditions
                )

            answer, created = Answer.objects.get_or_create(
                student=student,
                question=question,
                defaults={'content': ''} # 빈 답안으로 생성
            )
            
            note_content = request.POST.get('note', '')
            answer.note = note_content
            answer.save()
            
            return JsonResponse({
                'status': 'success', 
                'message': '메모가 저장되었습니다.',
                'answer_id': answer.id
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'fail'}, status=405)
'''
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
'''
