import base64
import io
from datetime import date, timedelta

from PIL import Image

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, School, Student, Subject
from .models import AttendanceReport, AttendanceReportFolder


class AttendanceReportFlowTests(TestCase):
    def setUp(self):
        image = Image.new('RGB', (200, 80), 'white')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        self.signature_data = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
        self.school = School.objects.create(
            office='테스트교육청', name='테스트학교', code='ATTENDANCE-TEST'
        )
        self.subject = Subject.objects.create(name='출결테스트과목')
        self.teacher = CustomUser.objects.create_user(
            username='attendance-teacher@example.com',
            email='attendance-teacher@example.com',
            password='test-password',
            name='담임교사',
            role=CustomUser.Role.TEACHER,
            school=self.school,
            subject=self.subject,
            is_approved=True,
        )
        self.student = Student.objects.create(
            teacher=self.teacher,
            school=self.school,
            grade=2,
            class_no=3,
            number=7,
            name='김학생',
            email='attendance-student@example.com',
        )
        self.student_user = CustomUser.objects.create_user(
            username='attendance-student',
            email=self.student.email,
            password='test-password',
            name=self.student.name,
            role=CustomUser.Role.STUDENT,
            school=self.school,
            subject=self.subject,
            is_approved=True,
        )

    def test_teacher_creates_folder_with_only_policy_and_targets(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('attendance_folder_create'), {
            'name': '2026학년도 출결자료',
            'operation_start_date': '2026-03-01',
            'operation_end_date': '2027-02-28',
            'allow_edit_after_submission': 'False',
            'target_students': [str(self.student.id)],
        })
        folder = AttendanceReportFolder.objects.get()
        self.assertRedirects(response, reverse('attendance_folder_detail', args=[folder.id]))
        self.assertEqual(folder.name, '2026학년도 출결자료')
        self.assertEqual(folder.operation_start_date, date(2026, 3, 1))
        self.assertEqual(folder.operation_end_date, date(2027, 2, 28))
        self.assertFalse(folder.allow_edit_after_submission)
        self.assertEqual(list(folder.target_students.all()), [self.student])

    def test_teacher_form_uses_folder_name_and_operation_period(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('attendance_folder_create'))
        self.assertContains(response, '폴더명')
        self.assertContains(response, '운영 기간')
        self.assertContains(response, '2026학년도 출결자료')
        self.assertNotContains(response, '질병지각')

    def test_teacher_can_update_folder_settings(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher,
            name='기존 폴더',
            operation_start_date=date(2026, 3, 1),
            operation_end_date=date(2026, 8, 31),
        )
        folder.target_students.add(self.student)
        self.client.force_login(self.teacher)

        response = self.client.post(reverse('attendance_folder_update', args=[folder.id]), {
            'name': '2026학년도 출결자료',
            'operation_start_date': '2026-03-02',
            'operation_end_date': '2027-02-28',
            'allow_edit_after_submission': 'False',
            'target_students': [str(self.student.id)],
        })

        folder.refresh_from_db()
        self.assertRedirects(response, reverse('attendance_folder_detail', args=[folder.id]))
        self.assertEqual(folder.name, '2026학년도 출결자료')
        self.assertEqual(folder.operation_start_date, date(2026, 3, 2))
        self.assertEqual(folder.operation_end_date, date(2027, 2, 28))
        self.assertFalse(folder.allow_edit_after_submission)

    def test_update_preserves_targets_when_student_fields_are_missing(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher,
            name='기존 폴더',
            operation_start_date=date(2026, 3, 1),
            operation_end_date=date(2027, 2, 28),
        )
        folder.target_students.add(self.student)
        self.client.force_login(self.teacher)

        response = self.client.post(reverse('attendance_folder_update', args=[folder.id]), {
            'name': '수정된 폴더',
            'operation_start_date': '2026-03-01',
            'operation_end_date': '2027-02-28',
            'allow_edit_after_submission': 'True',
        })

        self.assertRedirects(response, reverse('attendance_folder_detail', args=[folder.id]))
        self.assertEqual(list(folder.target_students.values_list('id', flat=True)), [self.student.id])

    def test_attendance_form_serializes_modal_selection_into_hidden_fields(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('attendance_folder_create'))
        self.assertContains(response, 'name="target_students_present"')
        self.assertContains(response, 'id="selectedStudentInputs"')
        self.assertContains(response, "input.name='target_students'", html=False)
        self.assertContains(response, 'event.preventDefault();sync();', html=False)

    def test_teacher_cannot_set_end_date_before_start_date(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('attendance_folder_create'), {
            'name': '잘못된 기간',
            'operation_start_date': '2026-12-31',
            'operation_end_date': '2026-03-01',
            'allow_edit_after_submission': 'True',
            'target_students': [str(self.student.id)],
        })
        self.assertContains(response, '운영 종료일은 시작일보다 빠를 수 없습니다.')
        self.assertFalse(AttendanceReportFolder.objects.exists())

    def test_student_submits_absence_report_and_can_print(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        self.client.force_login(self.student_user)
        response = self.client.post(reverse('student_attendance_report', args=[folder.id]), {
            'attendance_category': 'SICK',
            'attendance_kind': 'ABSENCE',
            'start_date': '2026-10-20',
            'end_date': '2026-10-22',
            'reason': '독감으로 자택에서 치료함',
            'written_date': '2026-10-23',
            'student_signature_data': self.signature_data,
        })
        report = AttendanceReport.objects.get()
        self.assertRedirects(response, reverse('student_attendance_report', args=[folder.id]))
        self.assertEqual(report.absence_days, 3)
        self.assertEqual(report.guardian_signature, '')
        self.assertEqual(report.student_signature_data, self.signature_data)
        self.assertIsNotNone(report.submitted_at)
        print_response = self.client.get(reverse('attendance_report_print', args=[report.id]))
        self.assertContains(print_response, '출결 확인 신고서')
        self.assertContains(print_response, '3일간')

    def test_locked_report_cannot_be_changed_after_submission(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher,
            allow_edit_after_submission=False,
        )
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder,
            student=self.student,
            attendance_type=AttendanceReport.AttendanceType.SICK_TARDY,
            start_date=date(2026, 10, 20),
            end_date=date(2026, 10, 20),
            start_period='1',
            end_period='2',
            reason='병원 진료',
            written_date=date(2026, 10, 20),
            student_signature='김학생',
            guardian_signature='김보호자',
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.student_user)
        self.client.post(reverse('student_attendance_report', args=[folder.id]), {
            'attendance_type': AttendanceReport.AttendanceType.SICK_LEAVE,
        })
        report.refresh_from_db()
        self.assertEqual(report.attendance_type, AttendanceReport.AttendanceType.SICK_TARDY)

    def test_guardian_qr_signature_and_teacher_confirmation(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher, allow_edit_after_submission=True)
        folder.target_students.add(self.student)
        student_url = reverse('student_attendance_report', args=[folder.id])
        self.client.force_login(self.student_user)
        response = self.client.post(student_url, {
            'attendance_category': 'RECOGNIZED', 'attendance_kind': 'TARDY',
            'single_date': '2026-10-20', 'start_period': '1', 'end_period': '2',
            'reason': '공식 대회 참가', 'written_date': '2026-10-20',
            'student_signature_data': self.signature_data,
        })
        self.assertEqual(response.status_code, 302)
        report = AttendanceReport.objects.get()
        self.assertEqual(report.attendance_type, AttendanceReport.AttendanceType.RECOGNIZED_TARDY)
        self.assertIsNone(report.guardian_signed_at)

        self.client.force_login(self.teacher)
        self.client.post(reverse('attendance_report_confirm', args=[report.id]))
        report.refresh_from_db()
        self.assertIsNone(report.confirmed_at)
        invite = self.client.post(reverse('attendance_report_guardian_invite', args=[report.id]))
        self.assertEqual(invite.status_code, 302)
        report.refresh_from_db()
        token = report.guardian_token
        self.assertTrue(token)
        detail = self.client.get(reverse('attendance_folder_detail', args=[folder.id]))
        self.assertContains(detail, reverse('attendance_guardian_sign', args=[token]))

        self.client.logout()
        guardian_url = reverse('attendance_guardian_sign', args=[token])
        self.assertContains(self.client.get(guardian_url), '공식 대회 참가')
        signed = self.client.post(guardian_url, {
            'guardian_name': '김보호자', 'guardian_signature_data': self.signature_data,
        })
        self.assertRedirects(signed, reverse('attendance_guardian_complete'))
        report.refresh_from_db()
        self.assertEqual(report.guardian_signature, '김보호자')
        self.assertIsNotNone(report.guardian_signed_at)
        self.assertIsNone(report.guardian_token)
        self.assertEqual(self.client.get(guardian_url).status_code, 410)

        self.client.force_login(self.teacher)
        self.client.post(reverse('attendance_report_confirm', args=[report.id]))
        report.refresh_from_db()
        self.assertIsNotNone(report.confirmed_at)
        self.client.force_login(self.student_user)
        self.assertContains(self.client.get(student_url), '교사 확정 완료')
        self.client.post(student_url, {'reason': '변경 시도'})
        report.refresh_from_db()
        self.assertEqual(report.reason, '공식 대회 참가')

    def test_student_revision_invalidates_existing_guardian_qr(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher, allow_edit_after_submission=True)
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student, attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 10, 20), end_date=date(2026, 10, 20),
            reason='기존 사유', written_date=date(2026, 10, 20),
            student_signature=self.student.name, student_signature_data=self.signature_data,
            submitted_at=timezone.now(), guardian_token='old-secret', guardian_token_created_at=timezone.now(),
        )
        self.client.force_login(self.student_user)
        self.client.post(reverse('student_attendance_report', args=[folder.id]), {
            'attendance_category': 'UNEXCUSED', 'attendance_kind': 'ABSENCE',
            'start_date': '2026-10-21', 'end_date': '2026-10-21',
            'reason': '새 사유', 'written_date': '2026-10-21',
            'student_signature_data': self.signature_data,
        })
        report.refresh_from_db()
        self.assertEqual(report.attendance_type, AttendanceReport.AttendanceType.UNEXCUSED_ABSENCE)
        self.assertIsNone(report.guardian_token)
        self.assertEqual(self.client.get(reverse('attendance_guardian_sign', args=['old-secret'])).status_code, 410)

    def test_guardian_link_expires_and_requires_real_signature_image(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student, attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 10, 20), end_date=date(2026, 10, 20),
            reason='병원 진료', written_date=date(2026, 10, 20),
            student_signature=self.student.name, student_signature_data=self.signature_data,
            submitted_at=timezone.now(), guardian_token='live-secret', guardian_token_created_at=timezone.now(),
        )
        link = reverse('attendance_guardian_sign', args=['live-secret'])
        invalid = self.client.post(link, {'guardian_name': '김보호자', 'guardian_signature_data': '김보호자'})
        self.assertContains(invalid, '보호자 서명을 손가락이나 펜으로 작성해 주세요.')
        report.refresh_from_db()
        self.assertIsNone(report.guardian_signed_at)
        report.guardian_token_created_at = timezone.now() - timedelta(days=8)
        report.save(update_fields=['guardian_token_created_at'])
        self.assertEqual(self.client.get(link).status_code, 410)

    def test_dashboard_template_contains_attendance_card(self):
        self.client.force_login(self.student_user)
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher,
            name='2026학년도 출결자료',
        )
        folder.target_students.add(self.student)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, '2026학년도 출결자료')
        self.assertContains(response, reverse('student_attendance_report', args=[folder.id]))

    def test_dashboard_hides_folder_outside_operation_period(self):
        today = timezone.localdate()
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher,
            name='운영 전 폴더',
            operation_start_date=today + timedelta(days=1),
            operation_end_date=today + timedelta(days=10),
        )
        folder.target_students.add(self.student)
        self.client.force_login(self.student_user)

        response = self.client.get(reverse('dashboard'))

        self.assertNotContains(response, '운영 전 폴더')
        report_response = self.client.get(reverse('student_attendance_report', args=[folder.id]))
        self.assertRedirects(report_response, reverse('dashboard'))

    def test_attendance_folders_are_returned_by_mega_menu_endpoint(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('get_menu_items'), {
            'category': 'ATTENDANCE',
            'sub': '출결 신고',
        })
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['items'][0]['url'], reverse('attendance_folder_detail', args=[folder.id]))
        self.assertIn('대상 1명', payload['items'][0]['detail_topic'])
