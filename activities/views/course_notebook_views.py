import json
import re
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import teacher_required
from accounts.models import Student
from ..models import (
    CourseNotebook, CourseNotebookMaterial, CourseNotebookPage,
    CourseNotebookSection, CourseNotebookStickyNote,
)
from .main_views import get_accessible_student_ids, get_student_tree


MATERIAL_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx'}
MATERIAL_MAX_SIZE = 25 * 1024 * 1024


def parse_section_outline(raw_outline):
    """Turn headings, bullets, or two-space indentation into a bounded section tree."""
    parsed = []
    previous_depth = 0
    for line_number, raw_line in enumerate((raw_outline or '').splitlines(), start=1):
        if not raw_line.strip():
            continue
        leading_spaces = len(raw_line.expandtabs(2)) - len(raw_line.expandtabs(2).lstrip(' '))
        stripped = raw_line.strip()
        heading = re.match(r'^(#{1,7})\s+(.+)$', stripped)
        if heading:
            requested_depth = len(heading.group(1)) - 1
            title = heading.group(2).strip()
        else:
            title = re.sub(r'^(?:[-*+]\s+|\d+[.)]\s+)', '', stripped).strip()
            requested_depth = leading_spaces // 2
        if not title:
            continue
        if len(title) > 100:
            raise ValueError(f'{line_number}번째 단원명은 100자 이내로 입력해 주세요.')
        depth = min(requested_depth, previous_depth + 1) if parsed else 0
        depth = min(depth, 6)
        parsed.append({'title': title, 'depth': depth})
        previous_depth = depth
        if len(parsed) > 100:
            raise ValueError('단원은 최대 100개까지 만들 수 있습니다.')
    return parsed


def create_sections(notebook, parsed_sections):
    parents = {}
    for position, item in enumerate(parsed_sections):
        depth = item['depth']
        section = CourseNotebookSection.objects.create(
            notebook=notebook,
            parent=parents.get(depth - 1) if depth else None,
            title=item['title'],
            depth=depth,
            position=position,
        )
        parents[depth] = section
        for stale_depth in [value for value in parents if value > depth]:
            del parents[stale_depth]


def validate_material(uploaded):
    extension = Path(uploaded.name).suffix.lower()
    if extension not in MATERIAL_EXTENSIONS:
        return f'{uploaded.name}: PDF, JPG, PNG, DOC, DOCX 파일만 첨부할 수 있습니다.'
    if uploaded.size > MATERIAL_MAX_SIZE:
        return f'{uploaded.name}: 파일 크기는 25MB 이하여야 합니다.'
    return None


@login_required
@teacher_required
def course_notebook_list(request):
    notebooks = CourseNotebook.objects.filter(
        teacher=request.user
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
        outline_text = request.POST.get('section_outline', '')
        materials = request.FILES.getlist('materials')
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
        if len(title) > 30:
            errors.append('노트 제목은 30자 이내로 입력해 주세요.')
        if len(subject) > 60 or len(description) > 1000:
            errors.append('입력 가능한 글자 수를 확인해 주세요.')
        try:
            parsed_sections = parse_section_outline(outline_text)
        except ValueError as error:
            parsed_sections = []
            errors.append(str(error))
        for uploaded in materials:
            material_error = validate_material(uploaded)
            if material_error:
                errors.append(material_error)
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
                create_sections(notebook, parsed_sections)
                for uploaded in materials:
                    CourseNotebookMaterial.objects.create(
                        notebook=notebook,
                        file=uploaded,
                        original_name=uploaded.name[:255],
                        content_type=(getattr(uploaded, 'content_type', '') or '')[:120],
                        size=uploaded.size,
                    )
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


def _student_profile_for(user):
    student = Student.objects.filter(email=user.email).first()
    return student or getattr(user, 'student', None)


@login_required
@require_http_methods(['GET', 'POST'])
def student_course_notebook(request, notebook_id):
    if getattr(request.user, 'role', None) != 'STUDENT':
        raise Http404
    student = _student_profile_for(request.user)
    if not student:
        messages.error(request, '학생 정보가 연결되어 있지 않습니다.')
        return redirect('dashboard')

    notebook = get_object_or_404(
        CourseNotebook.objects.select_related('teacher'),
        id=notebook_id,
        target_students=student,
        is_archived=False,
    )
    if request.method == 'POST':
        uploaded = request.FILES.get('image')
        memo = request.POST.get('memo', '').strip()
        section_id = request.POST.get('section', '').strip()
        section = notebook.sections.filter(id=section_id).first() if section_id else None
        if not uploaded:
            messages.error(request, '촬영한 노트 사진을 선택해 주세요.')
        elif not (getattr(uploaded, 'content_type', '') or '').startswith('image/'):
            messages.error(request, '이미지 파일만 업로드할 수 있습니다.')
        elif uploaded.size > 12 * 1024 * 1024:
            messages.error(request, '사진 한 장의 크기는 12MB 이하여야 합니다.')
        elif len(memo) > 200:
            messages.error(request, '메모는 200자 이내로 입력해 주세요.')
        elif section_id and not section:
            messages.error(request, '선택한 단원을 확인할 수 없습니다.')
        else:
            CourseNotebookPage.objects.create(
                notebook=notebook,
                student=student,
                section=section,
                image=uploaded,
                memo=memo,
            )
            messages.success(request, '노트 사진을 저장했습니다.')
            return redirect('student_course_notebook', notebook_id=notebook.id)

    pages = notebook.pages.filter(student=student).select_related('section').prefetch_related('sticky_notes')
    return render(request, 'activities/student_course_notebook.html', {
        'notebook': notebook,
        'student': student,
        'pages': pages,
        'sections': notebook.sections.all(),
        'materials': notebook.materials.all(),
        'sticky_colors': CourseNotebookStickyNote.COLOR_CHOICES,
    })


def _student_notebook_page(user, page_id):
    if getattr(user, 'role', None) != 'STUDENT':
        raise Http404
    student = _student_profile_for(user)
    if not student:
        raise Http404
    return get_object_or_404(
        CourseNotebookPage.objects.select_related('notebook'),
        id=page_id,
        student=student,
        notebook__target_students=student,
        notebook__is_archived=False,
    )


@login_required
@require_http_methods(['GET'])
def student_course_notebook_page(request, page_id):
    """사진과 구조화 텍스트를 나란히 확인·편집하는 학생 전용 페이지."""
    page = _student_notebook_page(request.user, page_id)
    page = CourseNotebookPage.objects.select_related(
        'notebook', 'section', 'student'
    ).prefetch_related('sticky_notes').get(id=page.id)
    return render(request, 'activities/student_course_notebook_page.html', {
        'page': page,
        'notebook': page.notebook,
        'sticky_colors': CourseNotebookStickyNote.COLOR_CHOICES,
    })


@login_required
@require_POST
def course_notebook_page_text_update(request, page_id):
    """학생이 OCR 결과를 확인하거나 직접 보완한 텍스트를 저장한다."""
    page = _student_notebook_page(request.user, page_id)
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'message': '요청 내용을 확인할 수 없습니다.'}, status=400)

    corrected_text = str(payload.get('text', '')).strip()
    if len(corrected_text) > 100_000:
        return JsonResponse({'message': '노트 텍스트는 100,000자 이내로 저장해 주세요.'}, status=400)

    page.ocr_corrected_text = corrected_text
    if corrected_text:
        page.ocr_status = CourseNotebookPage.OcrStatus.REVIEWED
    elif page.ocr_raw_text:
        page.ocr_status = CourseNotebookPage.OcrStatus.COMPLETED
    else:
        page.ocr_status = CourseNotebookPage.OcrStatus.UPLOADED
    page.save(update_fields=['ocr_corrected_text', 'ocr_status'])
    return JsonResponse({
        'message': '노트 텍스트를 저장했습니다.',
        'status': page.ocr_status,
        'status_label': page.get_ocr_status_display(),
    })


def _bounded_decimal(value, minimum, maximum):
    number = float(value)
    return round(max(minimum, min(maximum, number)), 2)


def _sticky_geometry(payload, defaults):
    width = _bounded_decimal(payload.get('width', defaults['width']), 12, 80)
    height = _bounded_decimal(payload.get('height', defaults['height']), 10, 80)
    return {
        'x': _bounded_decimal(payload.get('x', defaults['x']), 0, 100 - width),
        'y': _bounded_decimal(payload.get('y', defaults['y']), 0, 100 - height),
        'width': width,
        'height': height,
    }


@login_required
@require_POST
def course_notebook_sticky_create(request, page_id):
    page = _student_notebook_page(request.user, page_id)
    try:
        payload = json.loads(request.body or '{}')
        geometry = _sticky_geometry(payload, {'x': 8, 'y': 8, 'width': 32, 'height': 24})
        note = CourseNotebookStickyNote.objects.create(
            page=page,
            content=str(payload.get('content', ''))[:1000],
            **geometry,
            color=payload.get('color') if payload.get('color') in dict(CourseNotebookStickyNote.COLOR_CHOICES) else 'YELLOW',
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': '메모 정보가 올바르지 않습니다.'}, status=400)
    return JsonResponse({
        'status': 'success',
        'note': {'id': note.id, 'update_url': reverse('course_notebook_sticky_update', args=[note.id])},
    })


@login_required
@require_POST
def course_notebook_sticky_update(request, note_id):
    if getattr(request.user, 'role', None) != 'STUDENT':
        raise Http404
    student = _student_profile_for(request.user)
    if not student:
        raise Http404
    note = get_object_or_404(
        CourseNotebookStickyNote.objects.select_related('page'),
        id=note_id,
        page__student=student,
        page__notebook__target_students=student,
        page__notebook__is_archived=False,
    )
    try:
        payload = json.loads(request.body or '{}')
        if payload.get('delete'):
            note.delete()
            return JsonResponse({'status': 'success', 'deleted': True})
        note.content = str(payload.get('content', note.content))[:1000]
        geometry = _sticky_geometry(payload, {
            'x': note.x, 'y': note.y, 'width': note.width, 'height': note.height,
        })
        note.x = geometry['x']
        note.y = geometry['y']
        note.width = geometry['width']
        note.height = geometry['height']
        if payload.get('color') in dict(CourseNotebookStickyNote.COLOR_CHOICES):
            note.color = payload['color']
        note.save(update_fields=['content', 'x', 'y', 'width', 'height', 'color', 'updated_at'])
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': '메모 정보가 올바르지 않습니다.'}, status=400)
    return JsonResponse({'status': 'success'})
