from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, School, Student, Subject
from .models import AttendanceReport, AttendanceReportFolder


class AttendanceReportFlowTests(TestCase):
    def setUp(self):
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
            'allow_edit_after_submission': 'False',
            'target_students': [str(self.student.id)],
        })
        folder = AttendanceReportFolder.objects.get()
        self.assertRedirects(response, reverse('attendance_folder_detail', args=[folder.id]))
        self.assertFalse(folder.allow_edit_after_submission)
        self.assertEqual(list(folder.target_students.all()), [self.student])

    def test_teacher_form_shows_generic_attendance_names_only(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('attendance_folder_create'))
        for label in ['결석', '지각', '조퇴', '결과']:
            self.assertContains(response, label)
        self.assertNotContains(response, '질병지각')

    def test_student_submits_absence_report_and_can_print(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        self.client.force_login(self.student_user)
        response = self.client.post(reverse('student_attendance_report', args=[folder.id]), {
            'attendance_type': AttendanceReport.AttendanceType.SICK_ABSENCE,
            'start_date': '2026-10-20',
            'end_date': '2026-10-22',
            'reason': '독감으로 자택에서 치료함',
            'written_date': '2026-10-23',
            'student_signature': '김학생',
            'guardian_signature': '김보호자',
        })
        report = AttendanceReport.objects.get()
        self.assertRedirects(response, reverse('student_attendance_report', args=[folder.id]))
        self.assertEqual(report.absence_days, 3)
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

    def test_dashboard_template_contains_attendance_card(self):
        self.client.force_login(self.student_user)
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, '출결 확인 신고서')
        self.assertContains(response, reverse('student_attendance_report', args=[folder.id]))

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
