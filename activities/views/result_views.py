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