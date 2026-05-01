# 제출 현황 및 답안 관리 (activity_result, answer_detail 등)

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse

# 커스텀 데코레이터 및 모델 임포트
from accounts.decorators import teacher_required
from accounts.models import Student
from ..models import Activity, Answer

# [1] 제출 현황(답안) 목록 페이지
@login_required
@teacher_required
def activity_result(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    
    # 1. 필터 조건 가져오기
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')

    # 2. [핵심 수정] 필터나 검색어가 없을 경우 빈 목록 반환
    # (기존의 1학년 1반 자동 선택 로직을 삭제합니다)
    if not selected_targets and not name_query:
        target_students = Student.objects.none() # 빈 데이터셋
    else:
        # 필터링 로직 (기존 로직 유지)
        all_students = activity.target_students.all().order_by('grade', 'class_no', 'number')
        if not all_students.exists():
            all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')
        
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

        log_data = ""
        if answer:
            answer_id = answer.id
            note = answer.note
            absence = answer.absence_type
            log_data = answer.activity_log 
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
            'activity_log': log_data,
        })

    context = {
        'activity': activity,
        'submission_list': submission_list,
        'filter_data': filter_data,
        'selected_targets': selected_targets,
        'current_q': name_query,
    }
    return render(request, 'activities/activity_result.html', context)

# [2] 답안 상세 페이지
@login_required
@teacher_required
def answer_detail(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id)
    return render(request, 'activities/answer_detail.html', {'answer': answer})

# [3] 답안 삭제(폐기) 처리
@login_required
@teacher_required
def answer_delete(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id)
    activity = answer.question.activity
    
    # 리다이렉트 시 필요한 정보 미리 보관
    activity_id = activity.id
    cat = request.GET.get('category', activity.category)
    sub = request.GET.get('sub', activity.sub_category)
    
    # 답안 삭제
    answer.delete()
    
    messages.success(request, "답안을 삭제(반려)했습니다.")
    
    # 제출 현황으로 돌아갈 때 파라미터를 함께 전달하여 메뉴 활성화 유지
    return redirect(f'/activities/result/{activity_id}/?category={cat}&sub={sub}')

# [4] 선생님 특이사항 메모 저장 (AJAX)
@login_required
@teacher_required
def save_note(request, answer_id):
    if request.method == 'POST':
        try:
            answer = get_object_or_404(Answer, id=answer_id)
            # URLSearchParams 방식 혹은 JSON 방식에 따라 처리
            note_content = request.POST.get('note', '')
            answer.note = note_content
            answer.save()
            return JsonResponse({'status': 'success', 'message': '메모가 저장되었습니다.'})
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