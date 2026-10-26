from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.decorators import teacher_required
from accounts.models import Student
from ..models import AttendanceReport, AttendanceReportFolder
from .main_views import get_accessible_student_ids, get_student_tree


def _student_for_user(user):
    student = Student.objects.filter(email=user.email).first()
    return student or getattr(user, 'student', None)


def _period_rank(value):
    ordered = ['HOMEROOM'] + [str(number) for number in range(1, 11)] + ['CLOSING']
    try:
        return ordered.index(value)
    except ValueError:
        return -1


@login_required
@teacher_required
def attendance_folder_list(request):
    folders = list(
        AttendanceReportFolder.objects.filter(teacher=request.user)
        .prefetch_related('target_students', 'reports')
    )
    return render(request, 'activities/attendance_folder_list.html', {'folders': folders})


@login_required
@teacher_required
@require_http_methods(['GET', 'POST'])
def attendance_folder_create(request):
    selected_students = {str(value) for value in request.POST.getlist('target_students')}
    if request.method == 'POST':
        target_ids = get_accessible_student_ids(request.user, selected_students)
        if not target_ids:
            messages.error(request, '대상 학생을 한 명 이상 선택해 주세요.')
        else:
            folder = AttendanceReportFolder.objects.create(
                teacher=request.user,
                allow_edit_after_submission=request.POST.get('allow_edit_after_submission') == 'True',
            )
            folder.target_students.set(target_ids)
            messages.success(request, '출결신고서 폴더를 생성했습니다.')
            return redirect('attendance_folder_detail', folder_id=folder.id)

    return render(request, 'activities/attendance_folder_form.html', {
        'attendance_types': ('결석', '지각', '조퇴', '결과'),
        'student_tree': get_student_tree(request.user),
        'selected_students': selected_students,
        'allow_edit_after_submission': request.POST.get('allow_edit_after_submission', 'True'),
    })


@login_required
@teacher_required
def attendance_folder_detail(request, folder_id):
    folder = get_object_or_404(
        AttendanceReportFolder.objects.prefetch_related('target_students', 'reports__student'),
        id=folder_id,
        teacher=request.user,
    )
    reports_by_student = {report.student_id: report for report in folder.reports.all()}
    rows = [
        {'student': student, 'report': reports_by_student.get(student.id)}
        for student in folder.target_students.all().order_by('grade', 'class_no', 'number', 'name')
    ]
    return render(request, 'activities/attendance_folder_detail.html', {
        'folder': folder,
        'rows': rows,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def student_attendance_report(request, folder_id):
    if request.user.role != 'STUDENT':
        return redirect('attendance_folder_list')
    student = _student_for_user(request.user)
    if not student:
        messages.error(request, '연결된 학생 정보를 찾을 수 없습니다.')
        return redirect('dashboard')
    folder = get_object_or_404(
        AttendanceReportFolder,
        id=folder_id,
        target_students=student,
        is_active=True,
    )
    report = AttendanceReport.objects.filter(folder=folder, student=student).first()
    locked = bool(report and report.submitted_at and not folder.allow_edit_after_submission)

    if request.method == 'POST':
        if locked:
            messages.warning(request, '이 출결 신고서는 제출 후 수정할 수 없습니다.')
            return redirect('student_attendance_report', folder_id=folder.id)

        attendance_type = request.POST.get('attendance_type', '')
        start_date = request.POST.get('start_date', '')
        end_date = request.POST.get('end_date', '')
        start_period = request.POST.get('start_period', '')
        end_period = request.POST.get('end_period', '')
        reason = request.POST.get('reason', '').strip()
        written_date = request.POST.get('written_date', '')
        student_signature = request.POST.get('student_signature', '').strip()
        guardian_signature = request.POST.get('guardian_signature', '').strip()
        errors = []

        valid_types = {value for value, _label in AttendanceReport.AttendanceType.choices}
        valid_periods = {value for value, _label in AttendanceReport.Period.choices}
        if attendance_type not in valid_types:
            errors.append('출결명을 선택해 주세요.')
        try:
            parsed_start_date = date.fromisoformat(start_date)
        except ValueError:
            parsed_start_date = None
            errors.append('출결 날짜를 선택해 주세요.')
        try:
            parsed_written_date = date.fromisoformat(written_date)
        except ValueError:
            parsed_written_date = None
            errors.append('작성 날짜를 선택해 주세요.')

        parsed_end_date = None
        if attendance_type == AttendanceReport.AttendanceType.SICK_ABSENCE:
            try:
                parsed_end_date = date.fromisoformat(end_date)
            except ValueError:
                errors.append('결석 종료일을 선택해 주세요.')
            if parsed_start_date and parsed_end_date and parsed_end_date < parsed_start_date:
                errors.append('결석 종료일은 시작일보다 빠를 수 없습니다.')
            start_period = end_period = ''
        else:
            parsed_end_date = parsed_start_date
            if start_period not in valid_periods or end_period not in valid_periods:
                errors.append('시작 교시와 종료 교시를 선택해 주세요.')
            elif _period_rank(end_period) < _period_rank(start_period):
                errors.append('종료 교시는 시작 교시보다 빠를 수 없습니다.')

        if not reason:
            errors.append('출결 사유를 입력해 주세요.')
        if not student_signature:
            errors.append('학생 서명을 입력해 주세요.')
        if not guardian_signature:
            errors.append('보호자 서명을 입력해 주세요.')

        if not errors:
            report = report or AttendanceReport(folder=folder, student=student)
            report.attendance_type = attendance_type
            report.start_date = parsed_start_date
            report.end_date = parsed_end_date
            report.start_period = start_period
            report.end_period = end_period
            report.reason = reason
            report.written_date = parsed_written_date
            report.student_signature = student_signature
            report.guardian_signature = guardian_signature
            report.submitted_at = timezone.now()
            report.save()
            messages.success(request, '출결 확인 신고서를 제출했습니다.')
            return redirect('student_attendance_report', folder_id=folder.id)

        for error in errors:
            messages.error(request, error)
        form_values = request.POST
    else:
        form_values = None

    return render(request, 'activities/student_attendance_report.html', {
        'folder': folder,
        'student': student,
        'report': report,
        'locked': locked,
        'form_values': form_values,
        'attendance_types': AttendanceReport.AttendanceType.choices,
        'period_choices': AttendanceReport.Period.choices,
        'today': timezone.localdate(),
    })


@login_required
def attendance_report_print(request, report_id):
    report = get_object_or_404(
        AttendanceReport.objects.select_related('folder__teacher', 'student__school'),
        id=report_id,
        submitted_at__isnull=False,
    )
    if request.user.role == 'STUDENT':
        student = _student_for_user(request.user)
        if not student or report.student_id != student.id:
            return redirect('dashboard')
    elif report.folder.teacher_id != request.user.id:
        return redirect('attendance_folder_list')
    return render(request, 'activities/attendance_report_print.html', {'report': report})
