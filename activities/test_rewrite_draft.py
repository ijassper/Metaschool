from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Student
from .models import (
    Activity, Answer, AnswerRewriteDraft, AnswerSubmissionRevision,
    FeedbackResult, Question,
)


class RewriteDraftTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user(
            username='teacher@example.com', email='teacher@example.com',
            password='test-pass', role='TEACHER', name='Teacher',
        )
        self.student_user = user_model.objects.create_user(
            username='student@example.com', email='student@example.com',
            password='test-pass', role='STUDENT', name='Student',
        )
        self.student = Student.objects.create(
            email=self.student_user.email, grade=2, class_no=6, number=1, name='Student',
        )
        self.activity = Activity.objects.create(
            teacher=self.teacher, subject_name='국어', section='글쓰기', title='주제',
            q1_title='첫 문항', q2_title='', q3_title='',
        )
        self.activity.target_students.add(self.student)
        question = Question.objects.create(activity=self.activity, content='문항')
        self.answer = Answer.objects.create(
            student=self.student, question=question, ans_q1='기존 제출 답안',
            submitted_at=timezone.now(),
        )
        self.revision = AnswerSubmissionRevision.objects.create(
            answer=self.answer, version=1, submitted_at=self.answer.submitted_at,
            content_snapshot={'ans_q1': '기존 제출 답안', 'ans_q2': '', 'ans_q3': '', 'notebook_pages': []},
        )
        FeedbackResult.objects.create(
            activity=self.activity, student=self.student, answer=self.answer,
            answer_revision=self.revision, feedback_content='선생님 피드백',
            is_published=True, is_rewrite_assigned=True,
        )
        self.client.force_login(self.student_user)
        self.result_url = reverse('student_result_detail', args=[self.activity.id])
        self.draft_url = reverse('save_answer_rewrite_draft', args=[self.activity.id])

    def test_panel_starts_blank_and_shows_original_above_feedback(self):
        response = self.client.get(self.result_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h3 class="rewrite-column-title">학생 답안</h3>')
        self.assertContains(response, '기존 제출 답안')
        self.assertContains(response, '선생님 피드백')
        self.assertContains(response, '<textarea name="ans_q1"></textarea>', html=True)
        self.assertContains(response, 'data-rewrite-save-status')

    def test_draft_survives_reopen_without_changing_original_and_is_deleted_on_submit(self):
        response = self.client.post(self.draft_url, {'ans_q1': '새 고쳐쓰기 초안'})
        self.assertEqual(response.status_code, 200)
        draft = AnswerRewriteDraft.objects.get(answer=self.answer)
        self.assertEqual(draft.content_snapshot['ans_q1'], '새 고쳐쓰기 초안')
        self.answer.refresh_from_db()
        self.assertEqual(self.answer.ans_q1, '기존 제출 답안')

        response = self.client.get(self.result_url)
        self.assertContains(response, '<textarea name="ans_q1">새 고쳐쓰기 초안</textarea>', html=True)

        response = self.client.post(
            reverse('submit_answer_rewrite', args=[self.activity.id]),
            {'ans_q1': '완성한 새 답안'},
        )
        self.assertEqual(response.status_code, 200)
        self.answer.refresh_from_db()
        self.assertEqual(self.answer.ans_q1, '완성한 새 답안')
        self.assertFalse(AnswerRewriteDraft.objects.filter(answer=self.answer).exists())

    def test_only_assigned_student_can_save_rewrite_draft(self):
        other_user = get_user_model().objects.create_user(
            username='other@example.com', email='other@example.com',
            password='test-pass', role='STUDENT', name='Other',
        )
        Student.objects.create(email=other_user.email, grade=2, class_no=6, number=2, name='Other')
        self.client.force_login(other_user)
        response = self.client.post(self.draft_url, {'ans_q1': '남의 답안'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AnswerRewriteDraft.objects.exists())

    def test_rewrite_from_older_assigned_answer_keeps_newer_answer_version(self):
        newer_revision = AnswerSubmissionRevision.objects.create(
            answer=self.answer, version=2, submitted_at=timezone.now(),
            content_snapshot={'ans_q1': '답안2 내용', 'ans_q2': '', 'ans_q3': '', 'notebook_pages': []},
        )
        self.answer.ans_q1 = '답안2 내용'
        self.answer.save(update_fields=['ans_q1'])

        response = self.client.post(
            reverse('submit_answer_rewrite', args=[self.activity.id]),
            {'base_revision_id': self.revision.id, 'ans_q1': '답안1 피드백을 반영한 새 글'},
        )

        self.assertEqual(response.status_code, 200)
        revisions = list(self.answer.submission_revisions.order_by('version'))
        self.assertEqual([revision.version for revision in revisions], [1, 2, 3])
        self.assertEqual(revisions[1].id, newer_revision.id)
        self.assertEqual(revisions[1].content_snapshot['ans_q1'], '답안2 내용')
        self.assertEqual(revisions[2].content_snapshot['ans_q1'], '답안1 피드백을 반영한 새 글')

    def test_portfolio_groups_feedback_and_actions_by_answer_version(self):
        AnswerSubmissionRevision.objects.create(
            answer=self.answer, version=2, submitted_at=timezone.now(),
            content_snapshot={'ans_q1': '답안2 내용', 'ans_q2': '', 'ans_q3': '', 'notebook_pages': []},
        )
        self.answer.ans_q1 = '답안2 내용'
        self.answer.save(update_fields=['ans_q1'])
        self.activity.is_active = True
        self.activity.save(update_fields=['is_active'])

        response = self.client.get(self.result_url)

        self.assertContains(response, '최초 답안')
        self.assertContains(response, '고쳐쓰기1')
        self.assertContains(response, 'data-answer-tab="answer-')
        self.assertContains(response, '고쳐쓰기 과제')
        self.assertContains(response, '고쳐쓰기 완료')
        self.assertContains(response, 'bi-pencil-square')
