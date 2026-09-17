"""Owner-only replay and on-demand MP4 streaming (no retained video file)."""
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime, time, timedelta, timezone as datetime_timezone
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.decorators import teacher_required
from accounts.models import Student
from ..models import Activity, ProctorSnapshot


def recording_day_bounds(day):
    """Convert local midnight bounds in Python, not MySQL CONVERT_TZ."""
    zone = timezone.get_default_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), zone)
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), zone)
    return start.astimezone(datetime_timezone.utc), end.astimezone(datetime_timezone.utc)


def selected_recording(request, activity_id, student_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    # Include recorded students even if the target list was subsequently edited.
    frames = ProctorSnapshot.objects.filter(activity=activity, student_id=student_id).order_by('created_at', 'id')
    day = request.GET.get('date', '')
    if day:
        parsed = parse_date(day)
        if not parsed:
            raise ValueError('날짜 형식이 올바르지 않습니다.')
        start, end = recording_day_bounds(parsed)
        frames = frames.filter(created_at__gte=start, created_at__lt=end)
    return activity, frames


@login_required
@teacher_required
@require_GET
def proctor_replay(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    day = request.GET.get('date', '')
    try:
        selected_date = parse_date(day) if day else None
        if day and not selected_date:
            raise ValueError('invalid date')
    except ValueError:
        return JsonResponse({'message': '날짜 형식이 올바르지 않습니다.'}, status=400)
    if selected_date is None:
        latest = activity.proctor_snapshots.order_by('-created_at', '-id').first()
        selected_date = timezone.localdate(latest.created_at) if latest else timezone.localdate()
    start, end = recording_day_bounds(selected_date)
    recordings = ProctorSnapshot.objects.filter(
        activity=activity, student_id=OuterRef('pk'),
        created_at__gte=start, created_at__lt=end,
    )
    counts = recordings.order_by().values('student_id').annotate(total=Count('id'))
    # Preserve previously recorded students even after target roster changes.
    students = Student.objects.filter(
        Q(pk__in=activity.target_students.values('pk')) |
        Q(pk__in=activity.proctor_snapshots.order_by().values('student_id'))
    ).annotate(
        thumbnail_id=Subquery(recordings.order_by('created_at', 'id').values('id')[:1]),
        snapshot_count=Subquery(counts.values('total')[:1]),
    ).order_by('grade', 'class_no', 'number', 'name', 'id')
    response = render(request, 'activities/proctor_replay.html', {
        'activity': activity, 'students': students, 'selected_date': selected_date.isoformat(),
    })
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@teacher_required
@require_GET
def proctor_recording(request, activity_id, student_id):
    try:
        _, frames = selected_recording(request, activity_id, student_id)
    except ValueError as error:
        return JsonResponse({'message': str(error)}, status=400)
    response = JsonResponse({'frames': [
        {'time': frame.created_at.isoformat(), 'url': reverse('proctor_snapshot_image', args=[frame.id])}
        for frame in frames
    ], 'download_url': reverse('proctor_download', args=[activity_id, student_id])})
    response['Cache-Control'] = 'private, no-store'
    return response


def concat_manifest(frames):
    lines = ['ffconcat version 1.0']
    for index, frame in enumerate(frames):
        path = str(Path(frame.image.path).resolve()).replace('\\', '/').replace("'", "'\\''")
        lines.append(f"file '{path}'")
        duration = (frames[index + 1].created_at - frame.created_at).total_seconds() if index + 1 < len(frames) else 3
        lines.append(f'duration {max(0.1, duration):.3f}')
    lines.append(lines[-2])  # retain the final image for its duration
    return '\n'.join(lines) + '\n'


@login_required
@teacher_required
@require_GET
def proctor_download(request, activity_id, student_id):
    try:
        _, query = selected_recording(request, activity_id, student_id)
    except ValueError as error:
        return JsonResponse({'message': str(error)}, status=400)
    frames = list(query)
    if not frames:
        return JsonResponse({'message': '저장된 화면이 없습니다.'}, status=404)
    if (frames[-1].created_at - frames[0].created_at).total_seconds() > 14400:
        return JsonResponse({'message': '4시간 이내 기록만 다운로드할 수 있습니다. 날짜를 선택해 주세요.'}, status=400)
    executable = shutil.which(getattr(settings, 'PROCTOR_FFMPEG', 'ffmpeg'))
    if not executable:
        return JsonResponse({'message': '서버에 FFmpeg가 설치되지 않아 MP4 다운로드를 사용할 수 없습니다.'}, status=503)
    # Cross-worker, nonblocking export lock: at most one encoder per host.
    lock = open(Path(tempfile.gettempdir()) / 'ingrid-proctor-export.lock', 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            if not lock.read(1):
                lock.write(b'0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return JsonResponse({'message': '다른 영상이 생성 중입니다. 잠시 후 다시 시도해 주세요.'}, status=429)
    directory = tempfile.TemporaryDirectory(prefix='proctor-export-')
    process = None
    try:
        manifest = Path(directory.name) / 'frames.txt'
        manifest.write_text(concat_manifest(frames), encoding='utf-8')
        process = subprocess.Popen([
            executable, '-nostdin', '-loglevel', 'error', '-threads', '1',
            '-filter_threads', '1',
            '-f', 'concat', '-safe', '0', '-i', str(manifest),
            '-vf', 'scale=960:600:force_original_aspect_ratio=decrease,pad=960:600:(ow-iw)/2:(oh-ih)/2',
            '-r', '2', '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast',
            '-crf', '28', '-pix_fmt', 'yuv420p', '-an',
            '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4', 'pipe:1',
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (OSError, ValueError, NotImplementedError):
        directory.cleanup(); lock.close()
        return JsonResponse({'message': '영상 변환을 시작할 수 없습니다.'}, status=503)

    cleaned = False
    def cleanup():
        nonlocal cleaned
        if cleaned:
            return
        cleaned = True
        watchdog.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        directory.cleanup()
        lock.close()

    # Bound resource use even if a client disconnects or an encoder stalls.
    watchdog = threading.Timer(180, lambda: process.kill() if process.poll() is None else None)
    watchdog.daemon = True
    watchdog.start()
    first_chunk = process.stdout.read(65536)
    if not first_chunk:
        cleanup()
        return JsonResponse({'message': '영상 변환에 실패했습니다. 저장 이미지와 FFmpeg 설정을 확인해 주세요.'}, status=503)

    def stream():
        try:
            yield first_chunk
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            cleanup()

    response = StreamingHttpResponse(stream(), content_type='video/mp4')
    response._resource_closers.append(cleanup)
    response['Content-Disposition'] = f'attachment; filename="activity-{activity_id}-student-{student_id}.mp4"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Accel-Buffering'] = 'no'
    return response
