import json
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from activities.models import Activity
from .exam_views import get_student_for_activity


def normalize_typing_text(value):
    """Compare typing content without whitespace noise."""
    return ''.join(ch for ch in (value or '') if not ch.isspace())


def top_three(counter):
    return [
        {'key': key, 'count': count}
        for key, count in counter.most_common(3)
        if key
    ]


def grade_typing_speed(wpm):
    if wpm >= 300:
        return {
            'grade': '초고수 타자',
            'icon': '🎉',
            'tone': 'success',
            'message': '빵빠레! 목표치를 훌쩍 넘겼어요.',
            'confetti': True,
        }
    if wpm >= 200:
        return {
            'grade': '고속 타자',
            'icon': '👏',
            'tone': 'primary',
            'message': '박수! 아주 안정적인 속도예요.',
            'confetti': True,
        }
    if wpm >= 120:
        return {
            'grade': '약간 능숙',
            'icon': '👍',
            'tone': 'info',
            'message': '좋아요. 정확도를 유지하며 속도를 조금 더 올려 봅시다.',
            'confetti': False,
        }
    if wpm >= 60:
        return {
            'grade': '키보드 더듬더듬',
            'icon': '🙂',
            'tone': 'warning',
            'message': '기초 리듬이 잡히고 있어요. 조금만 더 연습해 볼까요?',
            'confetti': False,
        }
    return {
        'grade': '연습 필요',
        'icon': '😢',
        'tone': 'secondary',
        'message': '조금 더 연습해 볼까요? 천천히 정확하게 치는 것이 먼저예요.',
        'confetti': False,
    }


@require_POST
@login_required
def analyze_typing_result(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id)
    if not activity.typing_type:
        return JsonResponse({'status': 'error', 'message': '타자연습 활동이 아닙니다.'}, status=400)

    _, error_response = get_student_for_activity(request, activity)
    if error_response:
        return JsonResponse({'status': 'error', 'message': '분석 권한이 없습니다.'}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': '잘못된 분석 요청입니다.'}, status=400)

    target_text = normalize_typing_text(payload.get('target_text'))
    input_text = normalize_typing_text(payload.get('input_text'))
    total_time = max(float(payload.get('total_typing_time') or 0), 1.0)

    correct_counter = Counter()
    error_counter = Counter()
    correct_count = 0
    error_count = 0

    for index, typed_char in enumerate(input_text):
        target_char = target_text[index] if index < len(target_text) else ''
        if typed_char == target_char:
            correct_counter[target_char] += 1
            correct_count += 1
        else:
            error_counter[target_char or typed_char] += 1
            error_count += 1

    average_wpm = round(correct_count / max(total_time / 60, 1 / 60))
    accuracy = round((correct_count / len(input_text)) * 100) if input_text else 0
    grade = grade_typing_speed(average_wpm)

    return JsonResponse({
        'status': 'success',
        'average_wpm': average_wpm,
        'accuracy': accuracy,
        'error_count': error_count,
        'strong_keys': top_three(correct_counter),
        'weak_keys': top_three(error_counter),
        'grade': grade,
    })
