import json
import io
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import Http404
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase
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
