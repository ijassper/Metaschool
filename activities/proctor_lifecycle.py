from datetime import timedelta

from django.utils import timezone

from .models import Activity, ProctorSession


CAPTURE_LIMIT = timedelta(minutes=50)


def end_capture_sessions(activities, reason):
    now = timezone.now()
    return ProctorSession.objects.filter(activity__in=activities).exclude(
        status=ProctorSession.Status.ENDED,
    ).update(
        status=ProctorSession.Status.ENDED,
        capture_token='',
        ended_at=now,
        last_message=reason,
        updated_at=now,
    )


def end_expired_capture_sessions(activity):
    now = timezone.now()
    return ProctorSession.objects.filter(
        activity=activity,
        started_at__lte=now - CAPTURE_LIMIT,
    ).exclude(status=ProctorSession.Status.ENDED).update(
        status=ProctorSession.Status.ENDED,
        capture_token='',
        ended_at=now,
        last_message='감시 시작 후 50분 경과',
        updated_at=now,
    )


def end_teacher_capture(teacher):
    activities = Activity.objects.filter(teacher=teacher, proctor_mode=True)
    activities.update(proctor_capture_enabled=False)
    return end_capture_sessions(activities, '교사 로그아웃')
