from datetime import timedelta
import json
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.template.loader import get_template
from django.test import SimpleTestCase
from django.utils import timezone
from django.urls import reverse

from accounts.models import CustomUser, Student
from .models import Activity, Answer, ProctorSession, ProctorSnapshot, Question
from .views.exam_views import (
    finish_proctor_session_for_answer, get_proctor_diagnostics, open_proctor_capture_session,
)
from .views.result_views import get_proctor_connection_state
from .views.result_views import get_proctor_activity_for_user
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


class ProctorConnectionStateTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()

    def state(self, status=ProctorSession.Status.RECORDING, seconds_ago=0):
        return get_proctor_connection_state(
            status,
            self.now - timedelta(seconds=seconds_ago),
            self.now,
        )

    def test_recent_snapshot_is_live(self):
        self.assertEqual(self.state(seconds_ago=10), 'LIVE')

    def test_snapshot_between_thresholds_is_delayed(self):
        self.assertEqual(self.state(seconds_ago=11), 'DELAYED')
        self.assertEqual(self.state(seconds_ago=30), 'DELAYED')

    def test_old_snapshot_is_stopped(self):
        self.assertEqual(self.state(seconds_ago=31), 'STOPPED')

    def test_explicit_event_states_take_priority(self):
        self.assertEqual(self.state(ProctorSession.Status.AWAY), 'AWAY')
        self.assertEqual(self.state(ProctorSession.Status.ERROR), 'ERROR')
        self.assertEqual(self.state(ProctorSession.Status.ENDED), 'ENDED')
        self.assertEqual(self.state(ProctorSession.Status.DISCONNECTED), 'STOPPED')

    def test_submitted_answer_marks_ended_capture_without_hiding_reentry(self):
        self.assertEqual(
            get_proctor_connection_state(
                ProctorSession.Status.ENDED,
                self.now - timedelta(minutes=30),
                self.now,
                self.now - timedelta(minutes=31),
            ),
            'SUBMITTED',
        )
        self.assertEqual(
            get_proctor_connection_state(
                ProctorSession.Status.RECORDING,
                self.now - timedelta(seconds=3), self.now, self.now - timedelta(minutes=31),
            ),
            'LIVE',
        )

    def test_student_without_snapshot_has_no_record(self):
        self.assertEqual(
            get_proctor_connection_state(ProctorSession.Status.RECORDING, None, self.now),
            'NONE',
        )

    def test_security_states_are_independent_from_connection_state(self):
        self.assertEqual(ProctorSession.SecurityStatus.SECURE, 'SECURE')
        self.assertEqual(ProctorSession.SecurityStatus.PINNING_RELEASED, 'PINNING_RELEASED')
        self.assertEqual(ProctorSession.SecurityStatus.NOT_REQUIRED, 'NOT_REQUIRED')

    def test_monitor_template_exposes_summary_and_last_receipt(self):
        source = get_template('activities/proctor_monitor.html').template.source
        self.assertIn('summaryLive', source)
        self.assertIn('마지막 수신', source)
        self.assertIn('connection_state', source)
        self.assertIn('security_status', source)
        self.assertIn('화면 고정 해제', source)
        self.assertIn('submission-state', source)
        self.assertIn("SUBMITTED: ['state-ended', '녹화 종료']", source)
        self.assertIn('proctor-history-label', source)

    def test_device_diagnostics_are_allowlisted_and_bounded(self):
        diagnostics = get_proctor_diagnostics({
            'app_version': ' 0.2.0 ',
            'android_version': '14 (API 34)',
            'device_model': 'S' * 120,
            'capture_scope': 'FULL_DISPLAY',
            'android_id': 'must-not-be-stored',
        })
        self.assertEqual(diagnostics['app_version'], '0.2.0')
        self.assertEqual(len(diagnostics['device_model']), 100)
        self.assertNotIn('android_id', diagnostics)

    def test_admin_monitor_access_does_not_apply_teacher_filter(self):
        queryset = MagicMock()
        queryset.filter.return_value = queryset
        with patch('activities.views.result_views.Activity.objects.all', return_value=queryset), \
                patch('activities.views.result_views.get_object_or_404', return_value='activity') as get:
            result = get_proctor_activity_for_user(
                SimpleNamespace(role='ADMIN', is_superuser=False), 17
            )
        self.assertEqual(result, 'activity')
        queryset.filter.assert_not_called()
        get.assert_called_once_with(queryset, id=17)

    def test_teacher_monitor_access_is_limited_to_owned_activity(self):
        queryset = MagicMock()
        owned = MagicMock()
        queryset.filter.return_value = owned
        teacher = SimpleNamespace(role='TEACHER', is_superuser=False)
        with patch('activities.views.result_views.Activity.objects.all', return_value=queryset), \
                patch('activities.views.result_views.get_object_or_404', return_value='activity') as get:
            get_proctor_activity_for_user(teacher, 17)
        queryset.filter.assert_called_once_with(teacher=teacher)
        get.assert_called_once_with(owned, id=17)


class ProctorCaptureLeaseTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media.name,
            PROCTOR_STORAGE_ROOT=self.media.name,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        teacher = CustomUser.objects.create_user(
            username='proctor-teacher', email='proctor-teacher@example.com',
            password='test-password', name='담당 교사', role=CustomUser.Role.TEACHER,
            is_approved=True,
        )
        student_user = CustomUser.objects.create_user(
            username='proctor-student', email='proctor-student@example.com',
            password='test-password', name='김학생', role=CustomUser.Role.STUDENT,
            is_approved=True,
        )
        self.student = Student.objects.create(
            teacher=teacher, grade=2, class_no=6, number=1,
            name='김학생', email=student_user.email,
        )
        self.activity = Activity.objects.create(
            teacher=teacher, subject_name='국어', section='쓰기', title='감독 테스트',
            proctor_mode=True, allow_edit_after_submission=True, is_active=True,
        )
        self.activity.target_students.add(self.student)
        self.answer = Answer.objects.create(
            student=self.student,
            question=Question.objects.create(activity=self.activity, content='문항'),
        )
        self.client.force_login(student_user)

    def upload(self, token):
        return self.client.post(
            reverse('upload_proctor_snapshot', args=[self.activity.id]) + f'?capture_token={token}',
            {'snapshot': SimpleUploadedFile('screen.jpg', b'jpeg-data', content_type='image/jpeg')},
        )

    def test_submit_revokes_old_capture_and_reentry_issues_new_lease(self):
        first_token = open_proctor_capture_session(self.activity, self.student)
        self.assertEqual(self.upload(first_token).status_code, 200)
        self.assertEqual(ProctorSnapshot.objects.count(), 1)

        self.answer.submitted_at = timezone.now()
        self.answer.save(update_fields=['submitted_at'])
        finish_proctor_session_for_answer(self.answer)
        self.assertEqual(self.upload(first_token).status_code, 410)
        self.assertEqual(ProctorSnapshot.objects.count(), 1)

        reentry = self.client.get(reverse('take_test', args=[self.activity.id]))
        self.assertEqual(reentry.status_code, 200)
        second_token = reentry.context['proctor_capture_token']
        self.assertNotEqual(first_token, second_token)
        self.assertEqual(self.upload(first_token).status_code, 410)
        self.assertEqual(ProctorSnapshot.objects.count(), 1)
        ProctorSnapshot.objects.update(created_at=timezone.now() - timedelta(seconds=3))
        self.assertEqual(self.upload(second_token).status_code, 200)
        self.assertEqual(ProctorSnapshot.objects.count(), 2)

    def test_missing_lease_cannot_store_a_snapshot(self):
        self.assertEqual(self.upload('').status_code, 410)
        self.assertFalse(ProctorSnapshot.objects.exists())

    def test_answer_submission_closes_capture_before_redirect(self):
        token = open_proctor_capture_session(self.activity, self.student)
        response = self.client.post(
            reverse('take_test', args=[self.activity.id]),
            {'is_submit': 'true', 'ans_q1': '제출한 답안'},
        )
        self.assertEqual(response.status_code, 302)
        self.answer.refresh_from_db()
        self.assertIsNotNone(self.answer.submitted_at)
        session = ProctorSession.objects.get(activity=self.activity, student=self.student)
        self.assertEqual(session.status, ProctorSession.Status.ENDED)
        self.assertEqual(session.capture_token, '')
        self.assertEqual(self.upload(token).status_code, 410)

    def test_exit_submission_also_revokes_capture(self):
        token = open_proctor_capture_session(self.activity, self.student)
        response = self.client.post(
            reverse('log_activity'),
            data=json.dumps({'answer_id': self.answer.id, 'type': 'EXIT'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.answer.refresh_from_db()
        self.assertIsNotNone(self.answer.submitted_at)
        self.assertEqual(self.upload(token).status_code, 410)

    def test_expired_activity_and_stale_event_cannot_continue_capture(self):
        token = open_proctor_capture_session(self.activity, self.student)
        event_url = reverse('report_proctor_event', args=[self.activity.id])
        self.activity.deadline = timezone.now() - timedelta(seconds=1)
        self.activity.save(update_fields=['deadline'])
        self.assertEqual(self.upload(token).status_code, 410)
        self.assertFalse(ProctorSnapshot.objects.exists())

        self.activity.deadline = None
        self.activity.save(update_fields=['deadline'])
        finish_proctor_session_for_answer(self.answer)
        response = self.client.post(
            event_url + f'?capture_token={token}',
            data=json.dumps({'event_type': 'CAPTURE_STARTED'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            ProctorSession.objects.get(activity=self.activity, student=self.student).status,
            ProctorSession.Status.ENDED,
        )

    def test_stopped_capture_cannot_store_until_new_start_event(self):
        token = open_proctor_capture_session(self.activity, self.student)
        session = ProctorSession.objects.get(activity=self.activity, student=self.student)
        session.status = ProctorSession.Status.DISCONNECTED
        session.save(update_fields=['status'])
        self.assertEqual(self.upload(token).status_code, 409)
        self.assertFalse(ProctorSnapshot.objects.exists())

        response = self.client.post(
            reverse('report_proctor_event', args=[self.activity.id]) + f'?capture_token={token}',
            data=json.dumps({'event_type': 'CAPTURE_STARTED'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.upload(token).status_code, 200)
