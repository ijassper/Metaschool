import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Student
from .models import (
    Activity, Answer, AnswerSubmissionRevision, FeedbackResult, Question,
    submission_snapshot_content,
)


class SubmissionIntegrityTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user(
            username='teacher-integrity@example.com', email='teacher-integrity@example.com',
            password='test-pass', role='TEACHER', name='Teacher',
        )
        self.student_user = user_model.objects.create_user(
            username='student-integrity@example.com', email='student-integrity@example.com',
            password='test-pass', role='STUDENT', name='Student',
        )
        self.student = Student.objects.create(
            email=self.student_user.email, grade=2, class_no=6, number=23, name='Student',
        )
        self.activity = Activity.objects.create(
            teacher=self.teacher, subject_name='국어', section='글쓰기', title='주제',
            q1_title='첫 문항', q2_title='', q3_title='',
        )
        self.activity.target_students.add(self.student)
        self.question = Question.objects.create(activity=self.activity, content='문항')
        self.answer = Answer.objects.create(student=self.student, question=self.question)

    def test_back_button_security_log_does_not_submit_blank_answer(self):
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse('log_activity'),
            data=json.dumps({'answer_id': self.answer.id, 'type': 'BACK_BUTTON'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.answer.refresh_from_db()
        self.assertIsNone(self.answer.submitted_at)
        self.assertFalse(self.answer.submission_revisions.exists())
        self.assertIn('뒤로가기', self.answer.activity_log)

    def test_blank_submission_and_later_draft_are_distinguished(self):
        self.answer.submitted_at = timezone.now()
        self.answer.ans_q1 = '나중에 임시 저장한 답안'
        self.answer.save()
        AnswerSubmissionRevision.objects.create(
            answer=self.answer, version=1, submitted_at=self.answer.submitted_at,
            content_snapshot={'ans_q1': '', 'ans_q2': '', 'ans_q3': '', 'notebook_pages': []},
        )
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('answer_detail', args=[self.answer.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '제출 시점에 저장된 답안이 없습니다.')
        self.assertContains(response, '제출 이후 임시 저장된 내용')
        self.assertContains(response, '나중에 임시 저장한 답안')
        self.assertEqual(response.context['submitted_content'], '')

    def test_blank_notebook_page_does_not_hide_written_answer(self):
        snapshot = {
            'ans_q1': '제출한 글', 'ans_q2': '', 'ans_q3': '',
            'notebook_pages': [''],
        }
        self.assertEqual(submission_snapshot_content(snapshot, self.activity), '제출한 글')

    def test_feedback_cannot_attach_unsubmitted_draft_to_blank_revision(self):
        self.answer.submitted_at = timezone.now()
        self.answer.ans_q1 = '임시 저장한 답안'
        self.answer.save()
        AnswerSubmissionRevision.objects.create(
            answer=self.answer, version=1, submitted_at=self.answer.submitted_at,
            content_snapshot={'ans_q1': '', 'ans_q2': '', 'ans_q3': '', 'notebook_pages': []},
        )
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse('save_feedback_result', args=[self.answer.id]),
            data=json.dumps({'feedback_content': '피드백', 'task_type': 'feedback'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(FeedbackResult.objects.exists())

    @patch('activities.views.ai_views.get_monthly_ai_budget_status', return_value=None)
    def test_ai_draft_rejects_unsubmitted_answer_before_model_call(self, _budget):
        self.answer.submitted_at = timezone.now()
        self.answer.ans_q1 = '임시 저장한 답안'
        self.answer.save()
        AnswerSubmissionRevision.objects.create(
            answer=self.answer, version=1, submitted_at=self.answer.submitted_at,
            content_snapshot={'ans_q1': '', 'ans_q2': '', 'ans_q3': '', 'notebook_pages': []},
        )
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse('api_process_db_row'),
            data=json.dumps({
                'answer_id': self.answer.id,
                'task_type': 'feedback',
                'persist_feedback_session': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
