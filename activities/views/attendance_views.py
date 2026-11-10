import base64
import calendar
import io
import re
import secrets
from datetime import date, timedelta
from urllib.parse import urlencode

import qrcode
from PIL import Image, UnidentifiedImageError

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import teacher_required
from accounts.models import Student
from ..models import AttendanceReport, AttendanceReportFolder, AttendanceReportSequence
from .main_views import get_accessible_student_ids, get_student_tree


ATTENDANCE_CATEGORIES = [('SICK', '질병'), ('RECOGNIZED', '인정'), ('UNEXCUSED', '미인정')]
ATTENDANCE_KINDS = [('ABSENCE', '결석'), ('TARDY', '지각'), ('LEAVE', '조퇴'), ('RESULT', '결과')]
GUARDIAN_LINK_LIFETIME = timedelta(days=7)


def _valid_signature_data(value):
    if not re.fullmatch(r'data:image/png;base64,[A-Za-z0-9+/=]+', value or ''):
        return False
    try:
        raw = base64.b64decode(value.split(',', 1)[1], validate=True)
        if not raw or len(raw) > 200_000:
            return False
        with Image.open(io.BytesIO(raw)) as image:
            return image.format == 'PNG' and 1 <= image.width <= 2000 and 1 <= image.height <= 1000
    except (ValueError, UnidentifiedImageError, OSError):
        return False


def _guardian_link_is_active(report):
    return bool(
        report.guardian_token and report.guardian_token_created_at
        and not report.guardian_signed_at and not report.confirmed_at
        and timezone.now() < report.guardian_token_created_at + GUARDIAN_LINK_LIFETIME
    )


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
    folders.sort(key=lambda item: (item.academic_year or 0, item.created_at), reverse=True)
    return render(request, 'activities/attendance_folder_list.html', {
        'folders': folders,
    })


def _academic_year_period(year):
    return date(year, 3, 1), date(year + 1, 2, calendar.monthrange(year + 1, 2)[1])


@login_required
@teacher_required
@require_http_methods(['GET', 'POST'])
def attendance_folder_create(request):
    return _attendance_folder_form(request)


@login_required
@teacher_required
@require_http_methods(['GET', 'POST'])
def attendance_folder_update(request, folder_id):
    folder = get_object_or_404(AttendanceReportFolder, id=folder_id, teacher=request.user)
    return _attendance_folder_form(request, folder=folder)


def _attendance_folder_form(request, folder=None):
    today = timezone.localdate()
    current_academic_year = today.year if today.month >= 3 else today.year - 1
    existing_by_year = {
        item.academic_year: item
        for item in AttendanceReportFolder.objects.filter(
            teacher=request.user, academic_year__isnull=False,
        ).only('id', 'academic_year')
    }
    legacy_folders = list(AttendanceReportFolder.objects.filter(
        teacher=request.user, academic_year__isnull=True,
    ).only('id', 'operation_start_date', 'operation_end_date'))
    year_options = [
        {'year': year, 'start': _academic_year_period(year)[0], 'end': _academic_year_period(year)[1]}
        for year in range(current_academic_year + 1, 2019, -1)
    ]
    for option in year_options:
        option['existing_folder'] = (
            existing_by_year.get(option['year'])
            or next((
                item for item in legacy_folders
                if item.operation_start_date and item.operation_end_date
                and item.operation_start_date <= option['end']
                and item.operation_end_date >= option['start']
            ), None)
        )
    folder_by_selected_year = {option['year']: option['existing_folder'] for option in year_options}
    valid_years = set(folder_by_selected_year)
    selected_year = folder.academic_year if folder else current_academic_year
    if request.method == 'POST' and not folder:
        try:
            selected_year = int(request.POST.get('academic_year', ''))
        except (TypeError, ValueError):
            selected_year = None
    existing_students = (
        {str(value) for value in folder.target_students.values_list('id', flat=True)}
        if folder else set()
    )
    if request.method == 'POST':
        posted_students = {str(value) for value in request.POST.getlist('target_students')}
        selected_students = (
            existing_students
            if folder and not posted_students and 'target_students_present' not in request.POST
            else posted_students
        )
    else:
        selected_students = existing_students
    if request.method == 'POST':
        folder_name = request.POST.get('name', '').strip()
        target_ids = get_accessible_student_ids(request.user, selected_students)
        errors = []
        if not folder_name:
            errors.append('폴더명을 입력해 주세요.')
        if not folder and selected_year not in valid_years:
            errors.append('올바른 학년도를 선택해 주세요.')
        duplicate_folder = folder_by_selected_year.get(selected_year) if not folder else None
        if duplicate_folder:
            errors.append(
                '기존 학년도 미지정 폴더의 운영 기간이 겹칩니다. 기존 폴더를 확인해 주세요.'
                if duplicate_folder.academic_year is None else
                '해당 학년도의 출결신고서 폴더가 이미 있습니다. 대상 학생 변경 등은 기존 폴더에서 수정할 수 있습니다.'
            )
        if not target_ids:
            errors.append('대상 학생을 한 명 이상 선택해 주세요.')
        if not errors:
            creating = folder is None
            folder = folder or AttendanceReportFolder(teacher=request.user)
            folder.name = folder_name
            if creating:
                folder.academic_year = selected_year
                folder.operation_start_date, folder.operation_end_date = _academic_year_period(selected_year)
            try:
                with transaction.atomic():
                    folder.save()
                    folder.target_students.set(target_ids)
            except IntegrityError:
                duplicate_folder = AttendanceReportFolder.objects.filter(
                    teacher=request.user, academic_year=selected_year,
                ).first() if creating else None
                if not duplicate_folder:
                    raise
                folder = None
                next(option for option in year_options if option['year'] == selected_year)['existing_folder'] = duplicate_folder
                errors.append('해당 학년도의 출결신고서 폴더가 이미 있습니다. 기존 폴더를 수정해 주세요.')
            else:
                messages.success(
                    request,
                    '출결신고서 폴더를 생성했습니다.' if creating else '출결신고서 폴더 설정을 수정했습니다.',
                )
                return redirect('attendance_folder_detail', folder_id=folder.id)
        for error in errors:
            messages.error(request, error)
    else:
        duplicate_folder = folder_by_selected_year.get(selected_year) if not folder else None

    if folder:
        displayed_start, displayed_end = folder.operation_start_date, folder.operation_end_date
    elif selected_year in valid_years:
        displayed_start, displayed_end = _academic_year_period(selected_year)
    else:
        displayed_start, displayed_end = None, None

    return render(request, 'activities/attendance_folder_form.html', {
        'folder': folder,
        'is_edit': folder is not None,
        'student_tree': get_student_tree(request.user),
        'selected_students': selected_students,
        'academic_year': selected_year,
        'year_options': year_options,
        'duplicate_folder': duplicate_folder,
        'folder_name': request.POST.get(
            'name', folder.name if folder else f'{selected_year or current_academic_year}학년도 출결신고서',
        ),
        'operation_start_date': displayed_start,
        'operation_end_date': displayed_end,
    })


@login_required
@teacher_required
def attendance_folder_detail(request, folder_id):
    folder = get_object_or_404(
        AttendanceReportFolder.objects.prefetch_related('target_students', 'reports__student'),
        id=folder_id,
        teacher=request.user,
    )
    reports_by_student = {}
    submitted_student_ids = set()
    for report in folder.reports.all():
        reports_by_student.setdefault(report.student_id, []).append(report)
        if report.submitted_at:
            submitted_student_ids.add(report.student_id)
    view_mode = 'list' if request.GET.get('view') == 'list' else 'calendar'
    search_query = request.GET.get('q', '').strip()
    start_filter = request.GET.get('start_date', '').strip()
    end_filter = request.GET.get('end_date', '').strip()
    try:
        start_date = date.fromisoformat(start_filter) if start_filter else None
    except ValueError:
        start_date, start_filter = None, ''
    try:
        end_date = date.fromisoformat(end_filter) if end_filter else None
    except ValueError:
        end_date, end_filter = None, ''
    if start_date and end_date and end_date < start_date:
        end_date, end_filter = None, ''
    students = folder.target_students.all().order_by('grade', 'class_no', 'number', 'name')
    for token in search_query.split():
        match = Q(name__icontains=token)
        if token.isdigit():
            match |= Q(number=int(token))
        students = students.filter(match)
    rows = []
    for student in students:
        for report in reports_by_student.get(student.id) or [None]:
            if start_date or end_date:
                if not report or not report.submitted_at:
                    continue
                report_end = report.end_date or report.start_date
                if start_date and report_end < start_date or end_date and report.start_date > end_date:
                    continue
            row = {'student': student, 'report': report}
            if report and _guardian_link_is_active(report):
                row['guardian_url'] = request.build_absolute_uri(
                    reverse('attendance_guardian_sign', args=[report.guardian_token])
                )
                qr = io.BytesIO()
                qrcode.make(row['guardian_url']).save(qr, format='PNG')
                row['guardian_qr'] = base64.b64encode(qr.getvalue()).decode('ascii')
            rows.append(row)
    month_value = request.GET.get('month', '')
    try:
        month_date = date.fromisoformat(month_value + '-01')
    except ValueError:
        month_date = timezone.localdate().replace(day=1)
    month_start = month_date.replace(day=1)
    month_end = month_date.replace(day=calendar.monthrange(month_date.year, month_date.month)[1])
    calendar_weeks = []
    for week_dates in calendar.Calendar(firstweekday=0).monthdatescalendar(month_date.year, month_date.month):
        week_start, week_end = week_dates[0], week_dates[-1]
        visible_reports = [
            row['report'] for row in rows if row['report'] and row['report'].submitted_at
            and row['report'].start_date <= week_end
            and (row['report'].end_date or row['report'].start_date) >= week_start
        ]
        visible_reports.sort(key=lambda item: (item.start_date, -(item.end_date or item.start_date).toordinal(), item.student.number))
        lanes = []
        events = []
        overflow = [[] for _ in week_dates]
        for report in visible_reports:
            first_day = max(report.start_date, week_start)
            last_day = min(report.end_date or report.start_date, week_end)
            first_column = (first_day - week_start).days + 1
            last_column = (last_day - week_start).days + 1
            lane = next((index for index, occupied_until in enumerate(lanes) if occupied_until < first_column), len(lanes))
            if lane == len(lanes):
                lanes.append(last_column)
            else:
                lanes[lane] = last_column
            if lane < 3:
                events.append({
                    'report': report, 'column': first_column, 'span': last_column - first_column + 1,
                    'lane': lane + 1, 'category': report.attendance_category.lower(),
                    'label': f'{report.student.name} · {report.get_attendance_type_display()}',
                })
            else:
                for index in range(first_column - 1, last_column):
                    overflow[index].append(f'{report.student.name} · {report.get_attendance_type_display()}')
        calendar_weeks.append({
            'days': [
                {'date': day, 'in_month': day.month == month_date.month,
                 'overflow_count': len(overflow[index]), 'overflow_title': '\n'.join(overflow[index])}
                for index, day in enumerate(week_dates)
            ],
            'events': events,
        })
    base_filters = {'q': search_query, 'start_date': start_filter, 'end_date': end_filter}
    base_filters = {key: value for key, value in base_filters.items() if value}
    previous_month = month_start - timedelta(days=1)
    next_month = month_end + timedelta(days=1)
    calendar_base = reverse('attendance_folder_detail', args=[folder.id])
    def calendar_url(target_month):
        return calendar_base + '?' + urlencode({**base_filters, 'month': target_month.strftime('%Y-%m')})
    return render(request, 'activities/attendance_folder_detail.html', {
        'folder': folder,
        'rows': rows,
        'submitted_student_count': len(submitted_student_ids),
        'not_submitted_count': max(folder.target_students.count() - len(submitted_student_ids), 0),
        'view_mode': view_mode,
        'search_query': search_query,
        'start_filter': start_filter,
        'end_filter': end_filter,
        'month_label': month_start.strftime('%Y년 %m월'),
        'month_value': month_start.strftime('%Y-%m'),
        'calendar_weeks': calendar_weeks,
        'previous_month_url': calendar_url(previous_month),
        'next_month_url': calendar_url(next_month),
        'calendar_view_url': calendar_url(month_start),
        'list_view_url': calendar_base + '?' + urlencode({**base_filters, 'view': 'list', 'month': month_start.strftime('%Y-%m')}),
    })


@login_required
@teacher_required
@require_POST
def attendance_report_guardian_invite(request, report_id):
    report = get_object_or_404(AttendanceReport, id=report_id, folder__teacher=request.user, submitted_at__isnull=False)
    if report.confirmed_at or report.guardian_signed_at:
        messages.warning(request, '이미 보호자 서명 또는 교사 확정이 완료되었습니다.')
    else:
        report.guardian_token = secrets.token_urlsafe(32)
        report.guardian_token_created_at = timezone.now()
        report.save(update_fields=['guardian_token', 'guardian_token_created_at'])
        messages.success(request, '보호자 서명 QR을 만들었습니다. 내용을 확인한 뒤 보호자에게 전달해 주세요.')
    return redirect(_report_detail_url(report, request))


def _report_detail_url(report, request):
    params = {}
    if request.POST.get('view') == 'list':
        params['view'] = 'list'
    for key in ('q', 'start_date', 'end_date', 'month'):
        value = request.POST.get(key, '').strip()
        if value:
            params[key] = value
    query = '?' + urlencode(params) if params else ''
    return f"{reverse('attendance_folder_detail', args=[report.folder_id])}{query}#report-{report.id}"


@require_http_methods(['GET', 'POST'])
def attendance_guardian_sign(request, token):
    report = AttendanceReport.objects.select_related('folder', 'student').filter(
        guardian_token=token, submitted_at__isnull=False,
    ).first()
    if not report or not _guardian_link_is_active(report):
        return render(request, 'activities/attendance_guardian_sign.html', {'expired': True}, status=410)
    if request.method == 'POST':
        guardian_name = request.POST.get('guardian_name', '').strip()
        signature_data = request.POST.get('guardian_signature_data', '').strip()
        if not guardian_name or len(guardian_name) > 100:
            messages.error(request, '보호자 성명을 입력해 주세요.')
        elif not _valid_signature_data(signature_data):
            messages.error(request, '보호자 서명을 손가락이나 펜으로 작성해 주세요.')
        else:
            updated = AttendanceReport.objects.filter(
                id=report.id, guardian_token=token,
                guardian_signed_at__isnull=True, confirmed_at__isnull=True,
                guardian_token_created_at__gt=timezone.now() - GUARDIAN_LINK_LIFETIME,
            ).update(
                guardian_signature=guardian_name, guardian_signature_data=signature_data,
                guardian_signed_at=timezone.now(), guardian_token=None, guardian_token_created_at=None,
            )
            if updated:
                return redirect('attendance_guardian_complete')
            return render(request, 'activities/attendance_guardian_sign.html', {'expired': True}, status=410)
    return render(request, 'activities/attendance_guardian_sign.html', {'report': report})


@require_http_methods(['GET'])
def attendance_guardian_complete(request):
    return render(request, 'activities/attendance_guardian_complete.html')


@login_required
@teacher_required
@require_POST
def attendance_report_confirm(request, report_id):
    report = get_object_or_404(AttendanceReport, id=report_id, folder__teacher=request.user, submitted_at__isnull=False)
    if not report.guardian_signed_at:
        messages.error(request, '보호자 서명 후 확정할 수 있습니다.')
    elif not report.confirmed_at:
        report.confirmed_at = timezone.now()
        report.reopened_at = None
        report.save(update_fields=['confirmed_at', 'reopened_at'])
        messages.success(request, '출결 신고서를 확정했습니다. 학생 수정이 차단됩니다.')
    return redirect(_report_detail_url(report, request))


@login_required
@teacher_required
@require_POST
def attendance_report_unconfirm(request, report_id):
    report = get_object_or_404(AttendanceReport, id=report_id, folder__teacher=request.user, submitted_at__isnull=False)
    if report.confirmed_at:
        report.confirmed_at = None
        report.reopened_at = timezone.now()
        report.save(update_fields=['confirmed_at', 'reopened_at'])
        messages.success(request, '출결 신고서 확정을 취소했습니다. 학생이 다시 수정할 수 있습니다.')
    return redirect(_report_detail_url(report, request))


@login_required
def student_attendance_list(request):
    if request.user.role != 'STUDENT':
        return redirect('attendance_folder_list')
    student = _student_for_user(request.user)
    if not student:
        messages.error(request, '연결된 학생 정보를 찾을 수 없습니다.')
        return redirect('dashboard')
    folders = list(
        AttendanceReportFolder.objects.filter(target_students=student)
        .select_related('teacher').order_by('-created_at').distinct()
    )
    student_reports = list(AttendanceReport.objects.filter(
        folder__in=folders, student=student, submitted_at__isnull=False,
    ).select_related('folder__teacher').order_by('created_at', 'id'))
    sequence_by_year = {}
    for report in student_reports:
        year = report.folder.academic_year or report.start_date.year
        sequence_by_year[year] = sequence_by_year.get(year, 0) + 1
        report.display_number = report.report_number or (
            f'{year}-{student.grade}-{student.class_no:02d}-'
            f'{student.number:02d}-{sequence_by_year[year]:02d}'
        )
    new_report_folders = [folder for folder in folders if folder.is_within_operation_period]
    return render(request, 'activities/student_attendance_list.html', {
        'folders': folders, 'student': student,
        'reports': list(reversed(student_reports)),
        'submitted_count': len(student_reports),
        'new_report_folders': new_report_folders,
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
    folder = get_object_or_404(AttendanceReportFolder, id=folder_id, target_students=student)
    report_id = request.GET.get('report', '')
    if report_id:
        report = get_object_or_404(AttendanceReport, id=report_id, folder=folder, student=student)
    elif request.GET.get('new') == '1':
        report = None
    else:
        report = AttendanceReport.objects.filter(folder=folder, student=student).first()
    locked = bool(report and not report.can_edit)
    can_operate = folder.is_within_operation_period or bool(report and report.reopened_at and report.can_edit)
    if request.method == 'GET' and report and report.submitted_at and (
        request.GET.get('edit') != '1' or locked or not can_operate
    ):
        return redirect('attendance_report_print', report_id=report.id)
    if not can_operate:
        messages.warning(request, '현재 출결 신고서 운영 기간이 아닙니다.')
        return redirect('attendance_report_print', report_id=report.id) if report and report.submitted_at else redirect('dashboard')

    if request.method == 'POST':
        if locked:
            messages.warning(request, '확정된 출결 신고서는 수정할 수 없습니다.')
            return redirect('attendance_report_print', report_id=report.id)

        category = request.POST.get('attendance_category', '')
        kind = request.POST.get('attendance_kind', '')
        attendance_type = f'{category}_{kind}'
        start_date = request.POST.get('start_date', '') if kind == 'ABSENCE' else request.POST.get('single_date', '')
        end_date = request.POST.get('end_date', '')
        start_period = request.POST.get('start_period', '')
        end_period = request.POST.get('end_period', '')
        reason = request.POST.get('reason', '').strip()
        written_date = request.POST.get('written_date', '')
        student_signature = student.name
        student_signature_data = request.POST.get('student_signature_data', '').strip()
        guardian_name = request.POST.get('guardian_name', '').strip()
        guardian_signature_data = request.POST.get('guardian_signature_data', '').strip()
        errors = []

        valid_types = {value for value, _label in AttendanceReport.AttendanceType.choices}
        valid_periods = {value for value, _label in AttendanceReport.Period.choices}
        if category not in dict(ATTENDANCE_CATEGORIES) or kind not in dict(ATTENDANCE_KINDS) or attendance_type not in valid_types:
            errors.append('출결 구분과 종류를 각각 선택해 주세요.')
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
        if kind == 'ABSENCE':
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
        if not _valid_signature_data(student_signature_data):
            errors.append('학생 서명을 손가락이나 펜으로 작성해 주세요.')
        if len(guardian_name) > 100:
            errors.append('보호자 성명은 100자 이내로 입력해 주세요.')
        if guardian_signature_data and not _valid_signature_data(guardian_signature_data):
            errors.append('보호자 서명 이미지를 확인해 주세요.')

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
            report.student_signature_data = student_signature_data
            # Keep the guardian's drawn signature on the edit form; a newly issued QR is invalidated.
            previous_guardian_name = report.guardian_signature
            previous_guardian_data = report.guardian_signature_data
            previous_guardian_signed_at = report.guardian_signed_at
            report.guardian_signature = guardian_name
            report.guardian_signature_data = guardian_signature_data
            report.guardian_signed_at = (
                previous_guardian_signed_at
                if guardian_name == previous_guardian_name and guardian_signature_data == previous_guardian_data
                else timezone.now() if guardian_name and guardian_signature_data else None
            )
            report.guardian_token = None
            report.guardian_token_created_at = None
            report.submitted_at = timezone.now()
            with transaction.atomic():
                if not report.report_number:
                    year = folder.academic_year or parsed_start_date.year
                    Student.objects.select_for_update().get(pk=student.pk)
                    sequence, _ = AttendanceReportSequence.objects.select_for_update().get_or_create(
                        student=student, academic_year=year,
                    )
                    sequence.last_number += 1
                    sequence.save(update_fields=['last_number'])
                    report.report_number = (
                        f'{year}-{student.grade}-{student.class_no:02d}-'
                        f'{student.number:02d}-{sequence.last_number:02d}'
                    )
                report.save()
            messages.success(request, '출결 확인 신고서를 제출했습니다.')
            return redirect('attendance_report_print', report_id=report.id)

        for error in errors:
            messages.error(request, error)
        form_values = request.POST
    else:
        form_values = None

    guardian_signature_data_for_form = (
        form_values.get('guardian_signature_data', '') if form_values else
        report.guardian_signature_data if report else ''
    )

    return render(request, 'activities/student_attendance_report.html', {
        'folder': folder,
        'student': student,
        'report': report,
        'locked': locked,
        'form_values': form_values,
        'attendance_categories': ATTENDANCE_CATEGORIES,
        'attendance_kinds': ATTENDANCE_KINDS,
        'selected_category': form_values.get('attendance_category', '') if form_values else report.attendance_category if report else '',
        'selected_kind': form_values.get('attendance_kind', '') if form_values else report.attendance_kind if report else '',
        'period_choices': AttendanceReport.Period.choices,
        'guardian_signature_data_for_form': guardian_signature_data_for_form,
        'today': timezone.localdate(),
    })


@login_required
@require_POST
def student_attendance_report_delete(request, report_id):
    if request.user.role != 'STUDENT':
        return redirect('attendance_folder_list')
    student = _student_for_user(request.user)
    if not student:
        return redirect('dashboard')
    with transaction.atomic():
        report = get_object_or_404(
            AttendanceReport.objects.select_for_update().select_related('folder'),
            id=report_id, student=student, folder__target_students=student,
        )
        if report.confirmed_at or not (report.folder.is_within_operation_period or report.reopened_at):
            messages.error(request, '확정되었거나 운영 기간이 지난 신고서는 삭제할 수 없습니다.')
            return redirect('attendance_report_print', report_id=report.id)
        report.delete()
    messages.success(request, '출결 신고서를 삭제했습니다.')
    return redirect('student_attendance_list')


@login_required
def attendance_report_print(request, report_id):
    report = get_object_or_404(
        AttendanceReport.objects.select_related('folder__teacher', 'student__school'),
        id=report_id,
        submitted_at__isnull=False,
    )
    is_student = request.user.role == 'STUDENT'
    if is_student:
        student = _student_for_user(request.user)
        if not student or report.student_id != student.id:
            return redirect('dashboard')
    elif report.folder.teacher_id != request.user.id:
        return redirect('attendance_folder_list')
    can_student_edit = bool(
        is_student and (report.folder.is_within_operation_period or bool(report.reopened_at))
        and report.can_edit
        and report.folder.target_students.filter(id=report.student_id).exists()
    )
    return render(request, 'activities/attendance_report_print.html', {
        'report': report,
        'is_student': is_student,
        'is_popup': request.GET.get('popup') == '1' and not is_student,
        'can_student_edit': can_student_edit,
    })
