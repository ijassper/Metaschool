import base64
import importlib
import io
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, School, Student, Subject
from .models import AttendanceReport, AttendanceReportFolder, AttendanceReportSequence


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

    def test_teacher_creates_folder_with_targets(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('attendance_folder_create'), {
            'academic_year': '2026',
            'name': '2026학년도 출결자료',
            'target_students': [str(self.student.id)],
        })
        folder = AttendanceReportFolder.objects.get()
        self.assertRedirects(response, reverse('attendance_folder_detail', args=[folder.id]))
        self.assertEqual(folder.name, '2026학년도 출결자료')
        self.assertEqual(folder.academic_year, 2026)
        self.assertEqual(folder.operation_start_date, date(2026, 3, 1))
        self.assertEqual(folder.operation_end_date, date(2027, 2, 28))
        self.assertEqual(list(folder.target_students.all()), [self.student])

    def test_teacher_form_uses_folder_name_and_operation_period(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('attendance_folder_create'))
        self.assertContains(response, 'name="academic_year"')
        self.assertLess(response.content.decode().index('name="academic_year"'), response.content.decode().index('name="name"'))
        self.assertContains(response, '폴더명')
        self.assertContains(response, '운영 기간')
        self.assertContains(response, '2026학년도 출결신고서')
        self.assertNotContains(response, 'name="operation_start_date"')
        self.assertNotContains(response, 'name="operation_end_date"')
        self.assertNotContains(response, '질병지각')
        self.assertNotContains(response, '제출 후 수정 허용')
        self.assertNotContains(self.client.get(reverse('attendance_folder_list')), '<th>수정 허용</th>')
        management = self.client.get(reverse('attendance_folder_list'))
        self.assertContains(management, '출결신고서 폴더 관리')
        self.assertContains(management, '<th>학년도</th>', html=False)
        self.assertContains(management, '<th>운영 상태</th>', html=False)

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
            'academic_year': '2027',
            'name': '2026학년도 출결자료',
            'operation_start_date': '2026-03-02',
            'operation_end_date': '2027-02-28',
            'target_students': [str(self.student.id)],
        })

        folder.refresh_from_db()
        self.assertRedirects(response, reverse('attendance_folder_detail', args=[folder.id]))
        self.assertEqual(folder.name, '2026학년도 출결자료')
        self.assertIsNone(folder.academic_year)
        self.assertEqual(folder.operation_start_date, date(2026, 3, 1))
        self.assertEqual(folder.operation_end_date, date(2026, 8, 31))

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

    def test_teacher_cannot_override_calculated_operation_period(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('attendance_folder_create'), {
            'academic_year': '2027',
            'name': '2027학년도 출결신고서',
            'operation_start_date': '2026-12-31',
            'operation_end_date': '2026-03-01',
            'target_students': [str(self.student.id)],
        })
        folder = AttendanceReportFolder.objects.get()
        self.assertRedirects(response, reverse('attendance_folder_detail', args=[folder.id]))
        self.assertEqual(folder.operation_start_date, date(2027, 3, 1))
        self.assertEqual(folder.operation_end_date, date(2028, 2, 29))

    def test_duplicate_academic_year_guides_teacher_to_existing_folder(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, academic_year=2026, name='기존 폴더',
            operation_start_date=date(2026, 3, 1), operation_end_date=date(2027, 2, 28),
        )
        folder.target_students.add(self.student)
        self.client.force_login(self.teacher)
        self.assertNotContains(
            self.client.get(reverse('attendance_folder_list')),
            '이번 학년도 폴더가 이미 있습니다.',
        )
        create_url = reverse('attendance_folder_create')
        self.assertContains(self.client.get(create_url), reverse('attendance_folder_update', args=[folder.id]))
        response = self.client.post(create_url, {
            'academic_year': '2026', 'name': '중복 폴더',
            'target_students': [str(self.student.id)],
        })
        self.assertContains(response, '해당 학년도의 출결신고서 폴더가 이미 있습니다.')
        self.assertContains(response, reverse('attendance_folder_update', args=[folder.id]))
        self.assertEqual(AttendanceReportFolder.objects.count(), 1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttendanceReportFolder.objects.create(teacher=self.teacher, academic_year=2026)

    def test_legacy_folder_with_matching_period_is_shown_without_backfill(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, name='기존 출결 폴더',
            operation_start_date=date(2026, 10, 27), operation_end_date=date(2026, 11, 28),
        )
        folder.target_students.add(self.student)
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('attendance_folder_create'), {
            'academic_year': '2026', 'name': '새 폴더',
            'target_students': [str(self.student.id)],
        })
        self.assertContains(response, reverse('attendance_folder_update', args=[folder.id]))
        self.assertEqual(AttendanceReportFolder.objects.count(), 1)
        folder.refresh_from_db()
        self.assertIsNone(folder.academic_year)
        self.assertEqual(folder.operation_start_date, date(2026, 10, 27))

    def test_existing_2026_folder_data_migration_keeps_report_and_targets(self):
        folder = AttendanceReportFolder.objects.create(
            id=1, teacher=self.teacher, name='기존 출결 폴더',
            operation_start_date=date(2026, 10, 27),
            operation_end_date=date(2026, 11, 28),
        )
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student,
            attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 10, 27), end_date=date(2026, 10, 27),
            reason='치료', written_date=date(2026, 10, 27),
            student_signature=self.student.name, submitted_at=timezone.now(),
        )
        migration = importlib.import_module('activities.migrations.0049_normalize_2026_attendance_folder')
        editor = SimpleNamespace(connection=SimpleNamespace(alias='default'))
        migration.set_2026_academic_year(importlib.import_module('django.apps').apps, editor)
        folder.refresh_from_db()
        self.assertEqual(folder.academic_year, 2026)
        self.assertEqual(folder.operation_start_date, date(2026, 3, 2))
        self.assertEqual(folder.operation_end_date, date(2027, 2, 28))
        self.assertEqual(list(folder.target_students.all()), [self.student])
        self.assertTrue(AttendanceReport.objects.filter(id=report.id, folder=folder).exists())
        migration.restore_original_period(importlib.import_module('django.apps').apps, editor)
        folder.refresh_from_db()
        self.assertIsNone(folder.academic_year)
        self.assertEqual(folder.operation_start_date, date(2026, 10, 27))

    def test_target_student_update_preserves_existing_report(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, name='기존 폴더', academic_year=2026,
            operation_start_date=date(2026, 3, 1), operation_end_date=date(2027, 2, 28),
        )
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student,
            attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 10, 20), end_date=date(2026, 10, 20),
            reason='치료', written_date=date(2026, 10, 20),
            student_signature=self.student.name, submitted_at=timezone.now(),
        )
        transfer = Student.objects.create(
            teacher=self.teacher, school=self.school, grade=2, class_no=3,
            number=8, name='전학생', email='transfer@example.com',
        )
        self.client.force_login(self.teacher)
        self.client.post(reverse('attendance_folder_update', args=[folder.id]), {
            'name': folder.name, 'academic_year': '2027',
            'target_students_present': '1',
            'target_students': [str(self.student.id), str(transfer.id)],
        })
        folder.refresh_from_db()
        self.assertEqual(folder.academic_year, 2026)
        self.assertEqual(folder.operation_end_date, date(2027, 2, 28))
        self.assertEqual(set(folder.target_students.values_list('id', flat=True)), {self.student.id, transfer.id})
        self.assertTrue(AttendanceReport.objects.filter(id=report.id, folder=folder).exists())

    def test_academic_year_end_is_inclusive_and_new_submission_expires_next_day(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, academic_year=2027,
            operation_start_date=date(2027, 3, 1), operation_end_date=date(2028, 2, 29),
        )
        folder.target_students.add(self.student)
        with patch('activities.views.attendance_views.timezone.localdate', return_value=date(2027, 2, 28)):
            self.assertEqual(folder.operation_status, '예정')
            self.assertFalse(folder.is_within_operation_period)
        with patch('activities.views.attendance_views.timezone.localdate', return_value=date(2027, 3, 1)):
            self.assertEqual(folder.operation_status, '운영 중')
            self.assertTrue(folder.is_within_operation_period)
        with patch('activities.views.attendance_views.timezone.localdate', return_value=date(2028, 2, 29)):
            self.assertTrue(folder.is_within_operation_period)
        with patch('activities.views.attendance_views.timezone.localdate', return_value=date(2028, 3, 1)):
            self.assertFalse(folder.is_within_operation_period)
            self.assertEqual(folder.operation_status, '만료')
            self.client.force_login(self.student_user)
            url = reverse('student_attendance_report', args=[folder.id]) + '?new=1'
            self.assertRedirects(self.client.get(url), reverse('dashboard'))
            self.client.post(url, {
                'attendance_category': 'SICK', 'attendance_kind': 'ABSENCE',
                'start_date': '2028-02-29', 'end_date': '2028-02-29',
                'reason': '치료', 'written_date': '2028-02-29',
                'student_signature_data': self.signature_data,
            })
            self.assertFalse(AttendanceReport.objects.filter(folder=folder).exists())

    def test_other_teacher_cannot_update_folder_or_view_its_management_page(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher, academic_year=2026)
        other = CustomUser.objects.create_user(
            username='other-attendance-teacher@example.com',
            email='other-attendance-teacher@example.com', password='test-password',
            name='다른 교사', role=CustomUser.Role.TEACHER,
            school=self.school, subject=self.subject, is_approved=True,
        )
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('attendance_folder_update', args=[folder.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('attendance_folder_detail', args=[folder.id])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('attendance_folder_list')), folder.display_name)

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
        self.assertRedirects(response, reverse('attendance_report_print', args=[report.id]))
        self.assertEqual(report.absence_days, 3)
        self.assertEqual(report.guardian_signature, '')
        self.assertEqual(report.student_signature_data, self.signature_data)
        self.assertIsNotNone(report.submitted_at)
        print_response = self.client.get(reverse('attendance_report_print', args=[report.id]))
        self.assertContains(print_response, '출결 확인 신고서')
        self.assertContains(print_response, '3일간')
        self.assertContains(print_response, '첨부 증빙서류')
        self.assertContains(print_response, '□ 진료확인서')
        self.assertContains(print_response, '□ 보건실확인증')
        self.assertContains(print_response, reverse('student_attendance_report', args=[folder.id]) + f'?report={report.id}&amp;edit=1')
        self.assertContains(self.client.get(reverse('student_attendance_report', args=[folder.id]) + '?edit=1'), '수정 제출')
        self.assertContains(self.client.get(reverse('dashboard')), reverse('student_attendance_list'))
        self.assertContains(self.client.get(reverse('student_attendance_list')), reverse('attendance_report_print', args=[report.id]))

    def test_student_form_has_optional_guardian_fields_and_native_notice_tables(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        self.client.force_login(self.student_user)

        response = self.client.get(reverse('student_attendance_report', args=[folder.id]))

        self.assertContains(response, 'name="guardian_name"')
        self.assertContains(response, 'name="guardian_signature_data"')
        self.assertContains(response, '학부모 성명')
        self.assertContains(response, '학부모 서명')
        self.assertNotContains(response, 'name="guardian_name" required')
        self.assertContains(response, 'name="reason" rows="3"')
        self.assertContains(response, '<table class="privacy-table">', count=2, html=False)
        self.assertContains(response, '개인정보 수집·이용 사항 고지')
        self.assertContains(response, '민감정보 수집·이용 사항 고지')
        self.assertContains(response, '「개인정보 보호법」 제23조 제1항 제2호')

    def test_home_guardian_signature_is_retained_when_report_is_edited(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        url = reverse('student_attendance_report', args=[folder.id])
        self.client.force_login(self.student_user)
        payload = {
            'attendance_category': 'SICK', 'attendance_kind': 'ABSENCE',
            'start_date': '2026-10-20', 'end_date': '2026-10-21',
            'reason': '집에서 치료함', 'written_date': '2026-10-21',
            'student_signature_data': self.signature_data,
            'guardian_name': '김보호자', 'guardian_signature_data': self.signature_data,
        }
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        report = AttendanceReport.objects.get()
        self.assertIsNotNone(report.guardian_signed_at)
        self.assertIsNone(report.guardian_token)
        self.assertRedirects(self.client.get(url), reverse('attendance_report_print', args=[report.id]))
        self.assertContains(self.client.get(reverse('attendance_report_print', args=[report.id])),
                            'alt="보호자 서명"')

        edit_page = self.client.get(url + '?edit=1')
        self.assertContains(edit_page, f'name="guardian_signature_data" value="{self.signature_data}"')
        revised_payload = {**payload, 'reason': '수정한 사유'}
        self.client.post(url, revised_payload)
        report.refresh_from_db()
        self.assertIsNotNone(report.guardian_signed_at)
        self.assertEqual(report.guardian_signature, '김보호자')
        self.assertEqual(report.guardian_signature_data, self.signature_data)

        self.client.force_login(self.teacher)
        self.client.post(reverse('attendance_report_confirm', args=[report.id]))
        report.refresh_from_db()
        self.assertIsNotNone(report.confirmed_at)

    def test_confirmed_report_cannot_be_changed_until_teacher_cancels_confirmation(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
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
            guardian_signed_at=timezone.now(),
            confirmed_at=timezone.now(),
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.student_user)
        self.client.post(reverse('student_attendance_report', args=[folder.id]), {
            'attendance_type': AttendanceReport.AttendanceType.SICK_LEAVE,
        })
        report.refresh_from_db()
        self.assertEqual(report.attendance_type, AttendanceReport.AttendanceType.SICK_TARDY)
        print_url = reverse('attendance_report_print', args=[report.id])
        self.assertRedirects(self.client.get(reverse('student_attendance_report', args=[folder.id]) + '?edit=1'), print_url)
        self.assertNotContains(self.client.get(print_url), '신고서 수정')

        self.client.force_login(self.teacher)
        detail = self.client.get(reverse('attendance_folder_detail', args=[folder.id]) + '?view=list')
        self.assertContains(detail, '확정취소')
        self.assertNotContains(detail, '완료 · 확정')
        response = self.client.post(reverse('attendance_report_unconfirm', args=[report.id]))
        self.assertRedirects(response, reverse('attendance_folder_detail', args=[folder.id]) + f'#report-{report.id}')
        report.refresh_from_db()
        self.assertIsNone(report.confirmed_at)
        self.assertIsNotNone(report.guardian_signed_at)

        self.client.force_login(self.student_user)
        self.assertContains(self.client.get(print_url), '신고서 수정')
        self.assertContains(self.client.get(reverse('student_attendance_report', args=[folder.id]) + '?edit=1'), '수정 제출')
        self.client.post(reverse('student_attendance_report', args=[folder.id]), {
            'attendance_category': 'SICK', 'attendance_kind': 'TARDY',
            'single_date': '2026-10-20', 'start_period': '1', 'end_period': '2',
            'reason': '수정한 사유', 'written_date': '2026-10-20',
            'student_signature_data': self.signature_data,
        })
        report.refresh_from_db()
        self.assertEqual(report.reason, '수정한 사유')
        self.assertIsNone(report.guardian_signed_at)

    def test_only_own_teacher_can_cancel_confirmation_and_post_is_required(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student, attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 10, 20), end_date=date(2026, 10, 20),
            reason='기존 사유', written_date=date(2026, 10, 20),
            student_signature=self.student.name, submitted_at=timezone.now(), confirmed_at=timezone.now(),
        )
        url = reverse('attendance_report_unconfirm', args=[report.id])
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.student_user)
        self.client.post(url)
        report.refresh_from_db()
        self.assertIsNotNone(report.confirmed_at)

    def test_attendance_calendar_has_multiday_bar_and_filters(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student, attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 10, 20), end_date=date(2026, 10, 24),
            reason='치료', written_date=date(2026, 10, 20),
            student_signature=self.student.name, submitted_at=timezone.now(),
            guardian_signed_at=timezone.now(),
        )
        self.client.force_login(self.teacher)
        base = reverse('attendance_folder_detail', args=[folder.id])
        calendar_page = self.client.get(base + '?view=calendar&month=2026-10')
        self.assertContains(calendar_page, '2026년 10월')
        self.assertContains(calendar_page, 'calendar-event sick')
        self.assertContains(calendar_page, 'grid-column:2/span 5')
        self.assertContains(calendar_page, reverse('attendance_report_print', args=[report.id]))
        self.assertContains(calendar_page, 'month=2026-09')
        self.assertNotContains(self.client.get(base + '?view=calendar&month=2026-10&q=없는학생'), 'calendar-event sick')
        self.assertNotContains(self.client.get(base + '?view=calendar&month=2026-10&start_date=2026-10-25'), 'calendar-event sick')
        self.assertContains(self.client.get(base + '?view=calendar&month=2026-10&start_date=2026-10-24'), 'calendar-event sick')

    def test_attendance_status_list_has_no_submission_date_and_keeps_actions_together(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student, attendance_type=AttendanceReport.AttendanceType.RECOGNIZED_TARDY,
            start_date=date(2026, 10, 20), end_date=date(2026, 10, 20),
            start_period='1', end_period='2', reason='대회', written_date=date(2026, 10, 20),
            student_signature=self.student.name, submitted_at=timezone.now(), guardian_signed_at=timezone.now(),
        )
        self.client.force_login(self.teacher)
        page = self.client.get(reverse('attendance_folder_detail', args=[folder.id]) + '?view=list&q=김학생')
        self.assertContains(page, '<th>학년</th><th>반</th><th>번호</th><th>이름</th>', html=False)
        self.assertNotContains(page, '<th>제출일</th>')
        self.assertContains(page, '학생별 출결 통계')
        self.assertContains(page, '김학생 출결신고서 목록')
        self.assertContains(page, '수정하기')
        self.assertContains(page, '완료확정')
        self.assertContains(page, 'name="view" value="list"')
        result = self.client.post(reverse('attendance_report_confirm', args=[report.id]), {'view': 'list'})
        self.assertRedirects(result, reverse('attendance_folder_detail', args=[folder.id]) + f'?view=list#report-{report.id}')

    def test_attendance_statistics_group_reports_and_months_follow_academic_year(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, academic_year=2026, name='2026학년도 출결자료',
        )
        folder.target_students.add(self.student)
        for attendance_type, day in (
            (AttendanceReport.AttendanceType.SICK_ABSENCE, date(2026, 3, 8)),
            (AttendanceReport.AttendanceType.SICK_TARDY, date(2026, 3, 9)),
            (AttendanceReport.AttendanceType.RECOGNIZED_LEAVE, date(2027, 2, 3)),
        ):
            AttendanceReport.objects.create(
                folder=folder, student=self.student, attendance_type=attendance_type,
                start_date=day, end_date=day, reason='조회 테스트', written_date=day,
                student_signature=self.student.name, submitted_at=timezone.now(),
            )
        self.client.force_login(self.teacher)
        base = reverse('attendance_folder_detail', args=[folder.id])
        full = self.client.get(base)
        self.assertContains(full, '전체보기')
        self.assertContains(full, '조회 월')
        self.assertContains(full, '조회 시작일')
        self.assertContains(full, '조회 종료일')
        self.assertEqual(full.context['stats_rows'][0]['total'], 3)
        self.assertEqual(full.context['stats_rows'][0]['counts'], [1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0])
        march = self.client.get(base + '?view=list&query_month=3')
        self.assertEqual(march.context['start_filter'], '2026-03-01')
        self.assertEqual(march.context['end_filter'], '2026-03-31')
        self.assertEqual(march.context['stats_rows'][0]['total'], 2)
        february = self.client.get(base + '?view=list&query_month=2')
        self.assertEqual(february.context['start_filter'], '2027-02-01')
        self.assertEqual(february.context['end_filter'], '2027-02-28')
        self.assertEqual(february.context['stats_rows'][0]['counts'], [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0])

    def test_teacher_can_edit_pending_report_but_signed_report_is_locked(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student,
            attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 10, 20), end_date=date(2026, 10, 20),
            reason='기존 사유', written_date=date(2026, 10, 20),
            student_signature=self.student.name, student_signature_data=self.signature_data,
            submitted_at=timezone.now(), guardian_token='pending-teacher-edit',
            guardian_token_created_at=timezone.now(),
        )
        url = reverse('attendance_report_teacher_edit', args=[report.id])
        original_submitted_at = report.submitted_at
        self.client.force_login(self.student_user)
        self.assertNotEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(url), '출결 신고서 수정')
        response = self.client.post(url, {
            'attendance_category': 'RECOGNIZED', 'attendance_kind': 'TARDY',
            'single_date': '2026-11-03', 'start_period': '1', 'end_period': '2',
            'reason': '대회 참가', 'written_date': '2026-11-03',
        })
        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.attendance_type, AttendanceReport.AttendanceType.RECOGNIZED_TARDY)
        self.assertEqual(report.reason, '대회 참가')
        self.assertEqual(report.student_signature_data, self.signature_data)
        self.assertEqual(report.submitted_at, original_submitted_at)
        self.assertIsNone(report.guardian_token)
        report.guardian_signed_at = timezone.now()
        report.save(update_fields=['guardian_signed_at'])
        self.assertRedirects(self.client.get(url), reverse('attendance_folder_detail', args=[folder.id]) + f'?view=list&student={self.student.id}#report-{report.id}')
        self.client.post(url, {
            'attendance_category': 'SICK', 'attendance_kind': 'ABSENCE',
            'start_date': '2026-11-04', 'end_date': '2026-11-04',
            'reason': '잠금 무시', 'written_date': '2026-11-04',
        })
        report.refresh_from_db()
        self.assertEqual(report.reason, '대회 참가')

    def test_guardian_qr_signature_and_teacher_confirmation(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
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
        detail = self.client.get(reverse('attendance_folder_detail', args=[folder.id]) + '?view=list')
        self.assertContains(detail, reverse('attendance_guardian_sign', args=[token]))
        self.assertContains(detail, 'data-bs-target="#studentReportsPanel"')
        self.assertContains(detail, 'href="' + reverse('attendance_report_print', args=[report.id]) + '"')
        print_url = reverse('attendance_report_print', args=[report.id])
        self.assertContains(self.client.get(print_url), '제출 현황')
        self.assertNotContains(self.client.get(print_url + '?popup=1'), '제출 현황')

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
        print_url = reverse('attendance_report_print', args=[report.id])
        self.assertRedirects(self.client.get(student_url), print_url)
        self.assertContains(self.client.get(print_url), '교사 확정 완료')
        self.client.post(student_url, {'reason': '변경 시도'})
        report.refresh_from_db()
        self.assertEqual(report.reason, '공식 대회 참가')

    def test_student_revision_invalidates_existing_guardian_qr(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher)
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
        self.assertContains(response, '내 출결 신고서')
        self.assertContains(response, reverse('student_attendance_list'))
        self.assertContains(self.client.get(reverse('student_attendance_list')), '2026학년도 출결자료')
        self.assertContains(self.client.get(reverse('student_attendance_list')), reverse('student_attendance_report', args=[folder.id]))

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
        self.assertNotContains(response, reverse('student_attendance_list'))
        report_response = self.client.get(reverse('student_attendance_report', args=[folder.id]))
        self.assertRedirects(report_response, reverse('dashboard'))

    def test_student_attendance_list_keeps_past_reports_visible(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, name='지난 출결', operation_end_date=yesterday,
        )
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student, attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=yesterday, end_date=yesterday, reason='치료', written_date=yesterday,
            student_signature=self.student.name, submitted_at=timezone.now(),
        )
        self.client.force_login(self.student_user)
        self.assertContains(self.client.get(reverse('dashboard')), reverse('student_attendance_list'))
        page = self.client.get(reverse('student_attendance_list'))
        self.assertContains(page, '지난 출결')
        self.assertContains(page, reverse('attendance_report_print', args=[report.id]))
        self.assertNotContains(page, reverse('student_attendance_report', args=[folder.id]) + '?edit=1')
        self.client.force_login(self.teacher)
        self.assertRedirects(self.client.get(reverse('student_attendance_list')), reverse('attendance_folder_list'))

    def test_student_attendance_list_shows_report_summary_and_new_button(self):
        submitted_folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, name='2026학년도 출결자료',
        )
        new_folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, name='추가 출결자료',
        )
        submitted_folder.target_students.add(self.student)
        new_folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=submitted_folder, student=self.student,
            attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 3, 2), end_date=date(2026, 3, 5),
            reason='손목 부상으로 인한 염좌 치료', written_date=date(2026, 3, 7),
            student_signature=self.student.name, submitted_at=timezone.now(),
            confirmed_at=timezone.now(),
        )
        self.client.force_login(self.student_user)

        response = self.client.get(reverse('student_attendance_list'))

        self.assertContains(response, '<h1>내 출결 신고서 목록</h1>', html=False)
        self.assertContains(response, 'class="attendance-hero"')
        self.assertNotContains(response, '작성한 신고서와 새로 작성할 수 있는 출결 신고 폴더를 확인하세요.')
        self.assertContains(response, '새로운 출결 신고서 작성')
        self.assertContains(response, 'data-bs-target="#newReportFolderModal"')
        self.assertNotContains(response, '새로 작성할 신고서')
        self.assertContains(response, reverse('student_attendance_report', args=[new_folder.id]))
        self.assertContains(response, '2026-2-03-07-01')
        self.assertContains(response, '질병결석')
        self.assertContains(response, '2026.03.02. ~ 2026.03.05.')
        self.assertContains(response, '손목 부상으로 인한 염좌 치료')
        self.assertContains(response, reverse('attendance_report_print', args=[report.id]))
        self.assertContains(response, 'class="report-card-link"')
        self.assertNotContains(response, '>신고서 보기</a>')
        self.assertNotContains(response, '>수정하기</a>')

    def test_student_can_submit_multiple_reports_in_one_folder_and_edit_one(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher, name='연간 출결자료')
        folder.target_students.add(self.student)
        base_url = reverse('student_attendance_report', args=[folder.id])
        self.client.force_login(self.student_user)
        payload = {
            'attendance_category': 'SICK', 'attendance_kind': 'ABSENCE',
            'start_date': '2026-10-20', 'end_date': '2026-10-20',
            'reason': '첫 번째 치료', 'written_date': '2026-10-21',
            'student_signature_data': self.signature_data,
        }
        self.assertEqual(self.client.post(base_url + '?new=1', payload).status_code, 302)
        first_report = AttendanceReport.objects.get()
        self.assertEqual(self.client.post(base_url + '?new=1', {
            **payload, 'start_date': '2026-11-02', 'end_date': '2026-11-02',
            'reason': '두 번째 치료',
        }).status_code, 302)
        self.assertEqual(AttendanceReport.objects.filter(folder=folder, student=self.student).count(), 2)
        second_report = AttendanceReport.objects.exclude(id=first_report.id).get()
        list_page = self.client.get(reverse('student_attendance_list'))
        self.assertContains(list_page, '2026-2-03-07-01')
        self.assertContains(list_page, '2026-2-03-07-02')
        self.assertContains(list_page, 'class="report-card-link"', count=2)
        self.assertContains(list_page, '>수정하기</a>', count=2)
        self.assertNotContains(list_page, '>신고서 보기</a>')
        self.assertContains(list_page, '새로운 출결 신고서 작성')

        edit_url = base_url + f'?report={first_report.id}&edit=1'
        self.client.post(edit_url, {**payload, 'reason': '첫 번째 치료 수정'})
        first_report.refresh_from_db()
        self.assertEqual(first_report.reason, '첫 번째 치료 수정')
        self.assertEqual(first_report.report_number, '2026-2-03-07-01')
        self.assertEqual(second_report.report_number, '2026-2-03-07-02')
        self.assertEqual(AttendanceReport.objects.filter(folder=folder, student=self.student).count(), 2)

        self.client.force_login(self.teacher)
        detail = self.client.get(reverse('attendance_folder_detail', args=[folder.id]) + '?view=list')
        self.assertContains(detail, f'id="report-{first_report.id}"')
        self.assertContains(detail, f'id="report-{second_report.id}"')
        self.assertContains(detail, '제출 학생</span><strong>1명', html=False)

    def test_student_delete_keeps_report_numbers_and_uses_next_sequence(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher, name='연간 출결자료')
        folder.target_students.add(self.student)
        base_url = reverse('student_attendance_report', args=[folder.id])
        self.client.force_login(self.student_user)
        payload = {
            'attendance_category': 'SICK', 'attendance_kind': 'ABSENCE',
            'start_date': '2026-10-20', 'end_date': '2026-10-20',
            'reason': '치료', 'written_date': '2026-10-21',
            'student_signature_data': self.signature_data,
        }
        self.client.post(base_url + '?new=1', payload)
        first = AttendanceReport.objects.get()
        self.client.post(base_url + '?new=1', {**payload, 'reason': '두 번째 치료'})
        second = AttendanceReport.objects.exclude(id=first.id).get()
        delete_url = reverse('student_attendance_report_delete', args=[first.id])
        self.assertContains(self.client.get(base_url + f'?report={first.id}&edit=1'), delete_url)
        self.assertContains(self.client.get(reverse('attendance_report_print', args=[first.id])), '← 신고서 목록으로')
        self.assertEqual(self.client.get(delete_url).status_code, 405)
        self.assertRedirects(self.client.post(delete_url), reverse('student_attendance_list'))
        self.assertFalse(AttendanceReport.objects.filter(id=first.id).exists())
        self.client.post(base_url + '?new=1', {**payload, 'reason': '세 번째 치료'})
        third = AttendanceReport.objects.exclude(id=second.id).get()
        self.assertEqual(second.report_number, '2026-2-03-07-02')
        self.assertEqual(third.report_number, '2026-2-03-07-03')

    def test_student_cannot_delete_confirmed_or_expired_report(self):
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher, name='연간 출결자료')
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student,
            attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=date(2026, 10, 20), end_date=date(2026, 10, 20),
            reason='치료', written_date=date(2026, 10, 21),
            student_signature=self.student.name, submitted_at=timezone.now(),
            confirmed_at=timezone.now(),
        )
        self.client.force_login(self.student_user)
        delete_url = reverse('student_attendance_report_delete', args=[report.id])
        self.assertRedirects(self.client.post(delete_url), reverse('attendance_report_print', args=[report.id]))
        self.assertTrue(AttendanceReport.objects.filter(id=report.id).exists())
        report.confirmed_at = None
        report.save(update_fields=['confirmed_at'])
        folder.operation_end_date = timezone.localdate() - timedelta(days=1)
        folder.save(update_fields=['operation_end_date'])
        self.assertRedirects(self.client.post(delete_url), reverse('attendance_report_print', args=[report.id]))
        self.assertTrue(AttendanceReport.objects.filter(id=report.id).exists())
        self.client.force_login(self.teacher)
        self.assertRedirects(self.client.post(delete_url), reverse('attendance_folder_list'))

    def test_existing_reports_get_numbers_and_sequence_during_migration(self):
        folder = AttendanceReportFolder.objects.create(
            teacher=self.teacher, academic_year=2026, name='기존 출결자료',
        )
        folder.target_students.add(self.student)
        for day in (20, 21):
            AttendanceReport.objects.create(
                folder=folder, student=self.student,
                attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
                start_date=date(2026, 10, day), end_date=date(2026, 10, day),
                reason='치료', written_date=date(2026, 10, day),
                student_signature=self.student.name, submitted_at=timezone.now(),
            )
        migration = importlib.import_module('activities.migrations.0051_attendance_report_numbers')
        migration.assign_existing_numbers(apps, SimpleNamespace(connection=connection))
        self.assertEqual(
            list(AttendanceReport.objects.order_by('created_at', 'id').values_list('report_number', flat=True)),
            ['2026-2-03-07-01', '2026-2-03-07-02'],
        )
        self.assertEqual(
            AttendanceReportSequence.objects.get(student=self.student, academic_year=2026).last_number,
            2,
        )

    def test_cancel_confirmation_reopens_report_after_operation_period(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        folder = AttendanceReportFolder.objects.create(teacher=self.teacher, operation_end_date=yesterday)
        folder.target_students.add(self.student)
        report = AttendanceReport.objects.create(
            folder=folder, student=self.student, attendance_type=AttendanceReport.AttendanceType.SICK_ABSENCE,
            start_date=yesterday, end_date=yesterday, reason='치료', written_date=yesterday,
            student_signature=self.student.name, submitted_at=timezone.now(),
            guardian_signed_at=timezone.now(), confirmed_at=timezone.now(),
        )
        self.client.force_login(self.teacher)
        self.client.post(reverse('attendance_report_unconfirm', args=[report.id]))
        report.refresh_from_db()
        self.assertIsNotNone(report.reopened_at)
        self.client.force_login(self.student_user)
        print_url = reverse('attendance_report_print', args=[report.id])
        self.assertContains(self.client.get(print_url), '신고서 수정')
        self.assertContains(self.client.get(reverse('student_attendance_list')), '수정하기')
        self.assertContains(self.client.get(reverse('student_attendance_report', args=[folder.id]) + '?edit=1'), '수정 제출')

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
