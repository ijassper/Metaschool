from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.decorators import teacher_required
from ..models import CourseNotebook
from .main_views import get_accessible_student_ids, get_student_tree


@login_required
@teacher_required
def course_notebook_list(request):
    notebooks = CourseNotebook.objects.filter(
        teacher=request.user, is_archived=False
    ).prefetch_related('target_students')
    return render(request, 'activities/course_notebook_list.html', {'notebooks': notebooks})


@login_required
@teacher_required
@require_http_methods(['GET', 'POST'])
def course_notebook_create(request):
    current_year = timezone.localdate().year
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        subject = request.POST.get('subject', '').strip()
        description = request.POST.get('description', '').strip()
        semester = request.POST.get('semester', '')
        cover_color = request.POST.get('cover_color', '')
        try:
            academic_year = int(request.POST.get('academic_year', current_year))
        except (TypeError, ValueError):
            academic_year = 0
        errors = []
        if not title:
            errors.append('노트 이름을 입력해 주세요.')
        if not subject:
            errors.append('과목명을 입력해 주세요.')
        if not 2020 <= academic_year <= current_year + 1:
            errors.append('학년도를 올바르게 입력해 주세요.')
        if semester not in {value for value, _ in CourseNotebook.Semester.choices}:
            errors.append('학기를 선택해 주세요.')
        if cover_color not in {value for value, _ in CourseNotebook.COVER_COLOR_CHOICES}:
            errors.append('표지 색상을 선택해 주세요.')
        if len(title) > 120 or len(subject) > 60 or len(description) > 1000:
            errors.append('입력 가능한 글자 수를 확인해 주세요.')
        if not errors:
            target_ids = get_accessible_student_ids(request.user, request.POST.getlist('target_students'))
            with transaction.atomic():
                notebook = CourseNotebook.objects.create(
                    teacher=request.user,
                    title=title,
                    subject=subject,
                    academic_year=academic_year,
                    semester=semester,
                    description=description,
                    cover_color=cover_color,
                )
                notebook.target_students.set(target_ids)
            messages.success(request, '교과 수업 노트를 만들었습니다.')
            return redirect('course_notebook_list')
        for error in errors:
            messages.error(request, error)

    return render(request, 'activities/course_notebook_form.html', {
        'current_year': current_year,
        'student_tree': get_student_tree(request.user),
        'semester_choices': CourseNotebook.Semester.choices,
        'cover_choices': CourseNotebook.COVER_COLOR_CHOICES,
        'selected_students': {str(value) for value in request.POST.getlist('target_students')},
    })
