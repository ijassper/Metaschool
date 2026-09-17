import json
import io
from datetime import timedelta, datetime, date, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import Http404
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone

from .views import proctor_replay_views as views


class ReplayTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/')
        self.request.user = SimpleNamespace(is_authenticated=True, role='TEACHER', is_approved=True)

    def test_owner_filter_is_required(self):
        with patch.object(views, 'get_object_or_404', side_effect=Http404) as lookup:
            with self.assertRaises(Http404):
                views.proctor_recording(self.request, 3, 7)
            self.assertEqual(lookup.call_args.kwargs['teacher'], self.request.user)

    def test_invalid_date_rejected(self):
        self.request.GET = {'date': 'bad-date'}
        with patch.object(views, 'get_object_or_404'), patch.object(views.ProctorSnapshot.objects, 'filter'):
            response = views.proctor_recording(self.request, 3, 7)
        self.assertEqual(response.status_code, 400)

    def test_empty_recording(self):
        with patch.object(views, 'selected_recording', return_value=(None, [])):
            response = views.proctor_download(self.request, 3, 7)
        self.assertEqual(response.status_code, 404)

    @override_settings(TIME_ZONE='Asia/Seoul')
    def test_day_bounds_are_utc_and_half_open(self):
        start, end = views.recording_day_bounds(date(2026, 9, 17))
        self.assertEqual(start, datetime(2026, 9, 16, 15, tzinfo=datetime_timezone.utc))
        self.assertEqual(end, datetime(2026, 9, 17, 15, tzinfo=datetime_timezone.utc))
        recorded = datetime(2026, 9, 17, 11, 38, 25, tzinfo=datetime_timezone.utc)
        self.assertTrue(start <= recorded < end)
        self.assertFalse(start <= end < end)

    def test_recording_uses_range_not_database_date_conversion(self):
        self.request.GET = {'date': '2026-09-17'}
        query = MagicMock()
        with patch.object(views, 'get_object_or_404'), \
                patch.object(views.ProctorSnapshot.objects, 'filter', return_value=query):
            views.selected_recording(self.request, 3, 7)
        filters = query.order_by.return_value.filter.call_args.kwargs
        self.assertIn('created_at__gte', filters)
        self.assertIn('created_at__lt', filters)
        self.assertNotIn('created_at__date', filters)

    def test_date_range_sql_has_no_convert_tz(self):
        start, end = views.recording_day_bounds(date(2026, 9, 17))
        sql = str(views.ProctorSnapshot.objects.filter(created_at__gte=start, created_at__lt=end).query)
        self.assertNotIn('CONVERT_TZ', sql)

    def test_ffmpeg_unavailable_is_explained(self):
        frames = [SimpleNamespace(created_at=timezone.now())]
        with patch.object(views, 'selected_recording', return_value=(None, frames)), patch.object(views.shutil, 'which', return_value=None):
            response = views.proctor_download(self.request, 3, 7)
        self.assertEqual(response.status_code, 503)
        self.assertIn('FFmpeg', json.loads(response.content)['message'])

    def test_manifest_preserves_gaps_and_last_frame(self):
        now = timezone.now()
        frames = [SimpleNamespace(created_at=now, image=SimpleNamespace(path='first.jpg')),
                  SimpleNamespace(created_at=now + timedelta(seconds=9), image=SimpleNamespace(path='last.jpg'))]
        manifest = views.concat_manifest(frames)
        self.assertIn('duration 9.000', manifest)
        self.assertIn('duration 3.000', manifest)
        self.assertEqual(manifest.count('last.jpg'), 2)

    def test_replay_template_compiles(self):
        self.assertIn('MP4 다운로드', get_template('activities/proctor_replay.html').template.source)

    @override_settings(DEBUG=True)
    def test_cards_show_recorded_and_unrecorded_students(self):
        students = [SimpleNamespace(id=7, name='기록학생', grade=2, class_no=6, number=1,
                                    thumbnail_id=21, snapshot_count=12),
                    SimpleNamespace(id=8, name='미기록학생', grade=2, class_no=6, number=2,
                                    thumbnail_id=None, snapshot_count=None)]
        html = get_template('activities/proctor_replay.html').render({
            'activity': SimpleNamespace(id=3, section='활동', title='테스트'),
            'students': students, 'selected_date': '2026-09-17',
        })
        self.assertIn('value="2026-09-17"', html)
        self.assertIn('12장', html)
        self.assertIn('미기록학생 감독 기록 없음', html)
        self.assertIn('id="replayModal"', html)
        self.assertIn('loading="lazy"', html)
        self.assertEqual(html.count('class="replay-card"'), 2)

    def test_gallery_rejects_invalid_dates(self):
        self.request.GET = {'date': '2026-99-99'}
        with patch.object(views, 'get_object_or_404'):
            response = views.proctor_replay(self.request, 3)
        self.assertEqual(response.status_code, 400)

    def test_gallery_defaults_to_latest_local_recording_date(self):
        activity = MagicMock()
        # UTC evening belongs to the following day in Seoul.
        timestamp = datetime(2026, 9, 16, 23, 30, tzinfo=datetime_timezone.utc)
        activity.proctor_snapshots.order_by.return_value.first.return_value = SimpleNamespace(created_at=timestamp)
        with timezone.override('Asia/Seoul'), \
                patch.object(views, 'get_object_or_404', return_value=activity), \
                patch.object(views.ProctorSnapshot.objects, 'filter'), \
                patch.object(views.Student.objects, 'filter'), \
                patch.object(views, 'Subquery'), \
                patch.object(views, 'render') as render:
            views.proctor_replay(self.request, 3)
        self.assertEqual(render.call_args.args[2]['selected_date'], '2026-09-17')

    def test_mp4_is_streamed_and_resources_closed(self):
        frames = [SimpleNamespace(created_at=timezone.now(), image=SimpleNamespace(path='record.jpg'))]
        process = MagicMock()
        process.stdout = io.BytesIO(b'mp4-test-data')
        process.poll.return_value = 0
        with patch.object(views, 'selected_recording', return_value=(None, frames)), \
                patch.object(views.shutil, 'which', return_value='ffmpeg'), \
                patch.object(views.subprocess, 'Popen', return_value=process) as start:
            response = views.proctor_download(self.request, 3, 7)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), b'mp4-test-data')
            response.close()
        self.assertTrue(process.stdout.closed)
        self.assertIn('pipe:1', start.call_args.args[0])
        self.assertEqual(response['Content-Type'], 'video/mp4')

    def test_encoder_failure_returns_message(self):
        frames = [SimpleNamespace(created_at=timezone.now(), image=SimpleNamespace(path='record.jpg'))]
        process = MagicMock()
        process.stdout = io.BytesIO(b'')
        process.poll.return_value = 1
        with patch.object(views, 'selected_recording', return_value=(None, frames)), \
                patch.object(views.shutil, 'which', return_value='ffmpeg'), \
                patch.object(views.subprocess, 'Popen', return_value=process):
            response = views.proctor_download(self.request, 3, 7)
        self.assertEqual(response.status_code, 503)
        self.assertTrue(process.stdout.closed)
