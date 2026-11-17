from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, Student
from .models import Activity, ProctorSession
from .views.exam_views import open_proctor_capture_session


class ActivityTeacherPauseTests(TestCase):
    def setUp(self):
        self.teacher = CustomUser.objects.create_user(
            username='pause-teacher', email='pause-teacher@example.com',
            password='test-password', name='담당 교사', role=CustomUser.Role.TEACHER,
            is_approved=True,
        )
        self.student_user = CustomUser.objects.create_user(
            username='pause-student', email='pause-student@example.com',
            password='test-password', name='학생', role=CustomUser.Role.STUDENT,
            is_approved=True,
        )
        self.student = Student.objects.create(
            teacher=self.teacher, grade=2, class_no=1, number=1,
            name='학생', email=self.student_user.email,
        )
        now = timezone.now()
        self.activity = Activity.objects.create(
            teacher=self.teacher, subject_name='국어', section='쓰기', title='일시중지 테스트',
            start_time=now - timedelta(minutes=10), deadline=now + timedelta(minutes=50),
            is_active=True, proctor_mode=True, allow_edit_after_submission=False,
        )
        self.activity.target_students.add(self.student)
        self.toggle_url = reverse('toggle_activity_status', args=[self.activity.id])

    def test_pause_persists_through_schedule_sync_and_rejects_student_writes(self):
        token = open_proctor_capture_session(self.activity, self.student)
        self.client.force_login(self.teacher)
        response = self.client.post(self.toggle_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_paused'])
        self.activity.refresh_from_db()
        self.assertTrue(self.activity.is_paused)
        self.assertFalse(self.activity.is_attainable)
        self.assertFalse(self.activity.allow_edit_after_submission)
        session = ProctorSession.objects.get(activity=self.activity)
        self.assertEqual(session.capture_token, '')
        self.assertEqual(session.status, ProctorSession.Status.ENDED)

        Activity.sync_scheduled_states(Activity.objects.filter(pk=self.activity.pk))
        self.activity.refresh_from_db()
        self.assertTrue(self.activity.is_active)
        self.assertTrue(self.activity.is_paused)

        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse('take_test', args=[self.activity.id])).status_code, 302)
        self.assertEqual(self.client.post(reverse('save_answer_draft', args=[self.activity.id])).status_code, 403)
        self.assertEqual(self.client.post(
            reverse('upload_proctor_snapshot', args=[self.activity.id]) + f'?capture_token={token}',
            {'snapshot': SimpleUploadedFile('screen.jpg', b'jpeg-data', content_type='image/jpeg')},
        ).status_code, 410)

    def test_resume_preserves_original_deadline_and_edit_policy(self):
        deadline = self.activity.deadline
        self.client.force_login(self.teacher)
        self.client.post(self.toggle_url)
        response = self.client.post(self.toggle_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(response.json()['is_paused'])
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.deadline, deadline)
        self.assertFalse(self.activity.allow_edit_after_submission)
        self.assertTrue(self.activity.is_attainable)

    def test_toggle_requires_post_and_owner(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.toggle_url).status_code, 405)
        other_teacher = CustomUser.objects.create_user(
            username='other-teacher', email='other-teacher@example.com',
            password='test-password', name='다른 교사', role=CustomUser.Role.TEACHER,
            is_approved=True,
        )
        self.client.force_login(other_teacher)
        self.assertEqual(self.client.post(self.toggle_url).status_code, 404)

    def test_resume_after_deadline_remains_closed(self):
        self.activity.deadline = timezone.now() - timedelta(minutes=1)
        self.activity.is_paused = True
        self.activity.save(update_fields=['deadline', 'is_paused'])
        self.client.force_login(self.teacher)
        response = self.client.post(self.toggle_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.json()['status_code'], 'CLOSED')
        self.assertFalse(response.json()['is_attainable'])
