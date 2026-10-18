import json
import io
import re
from datetime import timedelta
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
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
from ..course_notebook_processing import (
    accept_native_document_scan, ensure_archive_image, process_course_notebook_page,
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


def sync_sections(notebook, parsed_sections):
    """Update the outline in place so existing page-to-section links survive when possible."""
    existing = list(notebook.sections.order_by('position', 'id'))
    active_sections = []
    parents = {}
    for position, item in enumerate(parsed_sections):
        depth = item['depth']
        parent = parents.get(depth - 1) if depth else None
        if position < len(existing):
            section = existing[position]
            section.title = item['title']
            section.depth = depth
            section.position = position
            section.parent = parent
            section.save(update_fields=['title', 'depth', 'position', 'parent'])
        else:
            section = CourseNotebookSection.objects.create(
                notebook=notebook,
                parent=parent,
                title=item['title'],
                depth=depth,
                position=position,
            )
        active_sections.append(section)
        parents[depth] = section
        for stale_depth in [value for value in parents if value > depth]:
            del parents[stale_depth]
    if len(existing) > len(active_sections):
        notebook.sections.filter(id__in=[section.id for section in existing[len(active_sections):]]).delete()


def serialize_section_outline(notebook):
    return '\n'.join(
        f"{'#' * (min(section.depth, 6) + 1)} {section.title}"
        for section in notebook.sections.order_by('position', 'id')
    )


def validate_material(uploaded):
    extension = Path(uploaded.name).suffix.lower()
    if extension not in MATERIAL_EXTENSIONS:
        return f'{uploaded.name}: PDF, JPG, PNG, DOC, DOCX 파일만 첨부할 수 있습니다.'
    if uploaded.size > MATERIAL_MAX_SIZE:
        return f'{uploaded.name}: 파일 크기는 25MB 이하여야 합니다.'
    return None


def read_notebook_submission(request, current_year):
    values = {
        'title': request.POST.get('title', '').strip(),
        'subject': request.POST.get('subject', '').strip(),
        'description': request.POST.get('description', '').strip(),
        'semester': request.POST.get('semester', ''),
        'cover_color': request.POST.get('cover_color', ''),
        'section_outline': request.POST.get('section_outline', ''),
    }
    materials = request.FILES.getlist('materials')
    try:
        values['academic_year'] = int(request.POST.get('academic_year', current_year))
    except (TypeError, ValueError):
        values['academic_year'] = 0
    errors = []
    if not values['title']:
        errors.append('노트 제목을 입력해 주세요.')
    if not values['subject']:
        errors.append('과목명을 입력해 주세요.')
    if not 2020 <= values['academic_year'] <= current_year + 1:
        errors.append('학년도를 올바르게 입력해 주세요.')
    if values['semester'] not in {value for value, _ in CourseNotebook.Semester.choices}:
        errors.append('학기를 선택해 주세요.')
    if values['cover_color'] not in {value for value, _ in CourseNotebook.COVER_COLOR_CHOICES}:
        errors.append('표지 색상을 선택해 주세요.')
    if len(values['title']) > 30:
        errors.append('노트 제목은 30자 이내로 입력해 주세요.')
    if len(values['subject']) > 60 or len(values['description']) > 1000:
        errors.append('입력 가능한 글자 수를 확인해 주세요.')
    try:
        parsed_sections = parse_section_outline(values['section_outline'])
    except ValueError as error:
        parsed_sections = []
        errors.append(str(error))
    for uploaded in materials:
        material_error = validate_material(uploaded)
        if material_error:
            errors.append(material_error)
    return values, parsed_sections, materials, errors


def notebook_form_context(request, current_year, *, notebook=None, form_values=None):
    if form_values is None:
        if notebook:
            form_values = {
                'academic_year': notebook.academic_year,
                'semester': notebook.semester,
                'subject': notebook.subject,
                'title': notebook.title,
                'description': notebook.description,
                'cover_color': notebook.cover_color,
                'section_outline': serialize_section_outline(notebook),
            }
        else:
            form_values = {
                'academic_year': current_year,
                'semester': CourseNotebook.Semester.YEAR,
                'subject': '',
                'title': '',
                'description': '',
                'cover_color': 'PURPLE',
                'section_outline': '',
            }
    selected_ids = (
        request.POST.getlist('target_students')
        if request.method == 'POST'
        else list(notebook.target_students.values_list('id', flat=True)) if notebook else []
    )
    return {
        'current_year': current_year,
        'student_tree': get_student_tree(request.user),
        'semester_choices': CourseNotebook.Semester.choices,
        'cover_choices': CourseNotebook.COVER_COLOR_CHOICES,
        'selected_students': {str(value) for value in selected_ids},
        'form_values': form_values,
        'notebook': notebook,
        'is_edit': notebook is not None,
        'existing_materials': notebook.materials.all() if notebook else [],
    }


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
        form_values, parsed_sections, materials, errors = read_notebook_submission(request, current_year)
        if not errors:
            target_ids = get_accessible_student_ids(request.user, request.POST.getlist('target_students'))
            with transaction.atomic():
                notebook = CourseNotebook.objects.create(
                    teacher=request.user,
                    title=form_values['title'],
                    subject=form_values['subject'],
                    academic_year=form_values['academic_year'],
                    semester=form_values['semester'],
                    description=form_values['description'],
                    cover_color=form_values['cover_color'],
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
    else:
        form_values = None

    return render(
        request,
        'activities/course_notebook_form.html',
        notebook_form_context(request, current_year, form_values=form_values),
    )


@login_required
@teacher_required
@require_http_methods(['GET', 'POST'])
def course_notebook_update(request, notebook_id):
    notebook = get_object_or_404(
        CourseNotebook.objects.prefetch_related('target_students', 'sections', 'materials'),
        id=notebook_id,
        teacher=request.user,
    )
    current_year = timezone.localdate().year
    if request.method == 'POST':
        form_values, parsed_sections, materials, errors = read_notebook_submission(request, current_year)
        delete_material_ids = {
            int(value) for value in request.POST.getlist('delete_materials') if value.isdigit()
        }
        if not errors:
            target_ids = get_accessible_student_ids(request.user, request.POST.getlist('target_students'))
            with transaction.atomic():
                notebook.title = form_values['title']
                notebook.subject = form_values['subject']
                notebook.academic_year = form_values['academic_year']
                notebook.semester = form_values['semester']
                notebook.description = form_values['description']
                notebook.cover_color = form_values['cover_color']
                notebook.save(update_fields=[
                    'title', 'subject', 'academic_year', 'semester',
                    'description', 'cover_color', 'updated_at',
                ])
                notebook.target_students.set(target_ids)
                sync_sections(notebook, parsed_sections)
                materials_to_delete = list(notebook.materials.filter(id__in=delete_material_ids))
                for material in materials_to_delete:
                    material.delete()
                    transaction.on_commit(lambda item=material: item.file.delete(save=False))
                for uploaded in materials:
                    CourseNotebookMaterial.objects.create(
                        notebook=notebook,
                        file=uploaded,
                        original_name=uploaded.name[:255],
                        content_type=(getattr(uploaded, 'content_type', '') or '')[:120],
                        size=uploaded.size,
                    )
            messages.success(request, '교과 수업 노트를 수정했습니다.')
            return redirect(f"{reverse('course_notebook_list')}#course-notebook-{notebook.id}")
        for error in errors:
            messages.error(request, error)
    else:
        form_values = None

    return render(
        request,
        'activities/course_notebook_form.html',
        notebook_form_context(
            request, current_year, notebook=notebook, form_values=form_values,
        ),
    )


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
    sections = list(notebook.sections.all())
    requested_section_id = (
        request.GET.get('section', '').strip()
        or request.POST.get('section', '').strip()
    )
    active_section = None
    if requested_section_id and requested_section_id != 'general':
        try:
            requested_section_pk = int(requested_section_id)
        except (TypeError, ValueError):
            raise Http404
        active_section = next(
            (section for section in sections if section.id == requested_section_pk), None
        )
        if not active_section:
            raise Http404
    if request.method == 'POST':
        uploads = request.FILES.getlist('image')
        native_document_scan = (
            request.POST.get('native_document_scan') == '1'
            and 'IngridStudentAndroid/' in request.META.get('HTTP_USER_AGENT', '')
        )
        memo = request.POST.get('memo', '').strip()
        if not uploads:
            messages.error(request, '촬영한 노트 사진을 선택해 주세요.')
        elif len(uploads) > 30:
            messages.error(request, '한 번에 최대 30장까지 올릴 수 있습니다.')
        elif any(not (getattr(uploaded, 'content_type', '') or '').startswith('image/') for uploaded in uploads):
            messages.error(request, '모든 파일이 이미지인지 확인해 주세요.')
        elif any(uploaded.size > 12 * 1024 * 1024 for uploaded in uploads):
            messages.error(request, '사진 한 장의 크기는 12MB 이하여야 합니다.')
        elif len(memo) > 200:
            messages.error(request, '메모는 200자 이내로 입력해 주세요.')
        elif sections and not active_section:
            messages.error(request, '목차에서 노트를 저장할 단원을 선택해 주세요.')
        else:
            with transaction.atomic():
                created_pages = [CourseNotebookPage.objects.create(
                    notebook=notebook, student=student, section=active_section,
                    image=uploaded, memo=memo,
                ) for uploaded in uploads]
                if native_document_scan:
                    for page in created_pages:
                        accept_native_document_scan(page)
            messages.success(request, f'노트 사진 {len(created_pages)}장을 저장했습니다. A4 문서로 정리합니다.')
            page_url = reverse('student_course_notebook_page', args=[created_pages[0].id])
            return redirect(f'{page_url}?uploaded={len(created_pages)}')

    all_pages = list(notebook.pages.filter(student=student).select_related('section'))
    common_context = {
        'notebook': notebook,
        'student': student,
        'sections': sections,
        'materials': notebook.materials.all(),
        'sticky_colors': CourseNotebookStickyNote.COLOR_CHOICES,
    }
    if active_section or (not sections and requested_section_id == 'general'):
        section_pages = [page for page in all_pages if page.section_id == getattr(active_section, 'id', None)]
        return render(request, 'activities/student_course_notebook_section.html', {
            **common_context,
            'active_section': active_section,
            'pages': section_pages,
            'section_query_value': active_section.id if active_section else 'general',
        })

    pages_by_section = {}
    unassigned_pages = []
    for page in all_pages:
        if page.section_id:
            pages_by_section.setdefault(page.section_id, []).append(page)
        else:
            unassigned_pages.append(page)
    section_items = [
        {'section': section, 'pages': pages_by_section.get(section.id, [])}
        for section in sections
    ]
    return render(request, 'activities/student_course_notebook.html', {
        **common_context,
        'section_items': section_items,
        'unassigned_pages': unassigned_pages,
        'total_page_count': len(all_pages),
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
    """학생의 여러 촬영 페이지를 A4 책장 형태로 보여준다."""
    page = _student_notebook_page(request.user, page_id)
    page = CourseNotebookPage.objects.select_related(
        'notebook', 'section', 'student'
    ).prefetch_related('sticky_notes').get(id=page.id)
    archive_pages = list(CourseNotebookPage.objects.filter(
        notebook=page.notebook, student=page.student,
    ).select_related('section').order_by('created_at', 'id'))
    current_index = next(index for index, item in enumerate(archive_pages) if item.id == page.id)
    try:
        uploaded_count = int(request.GET.get('uploaded', '0'))
    except (TypeError, ValueError):
        uploaded_count = 0
    if not 1 <= uploaded_count <= 30:
        uploaded_count = 0
    return render(request, 'activities/student_course_notebook_page.html', {
        'page': page,
        'notebook': page.notebook,
        'archive_pages': archive_pages,
        'current_number': current_index + 1,
        'page_count': len(archive_pages),
        'previous_page': archive_pages[current_index - 1] if current_index else None,
        'next_page': archive_pages[current_index + 1] if current_index + 1 < len(archive_pages) else None,
        'uploaded_count': uploaded_count,
    })


@login_required
@require_http_methods(['GET'])
def course_notebook_archive_pdf(request, notebook_id):
    """학생 본인의 노트 이미지를 시간순 A4 PDF 한 파일로 묶는다."""
    if getattr(request.user, 'role', None) != 'STUDENT':
        raise Http404
    student = _student_profile_for(request.user)
    notebook = get_object_or_404(
        CourseNotebook, id=notebook_id, target_students=student, is_archived=False,
    )
    pages = list(CourseNotebookPage.objects.filter(
        notebook=notebook, student=student,
    ).order_by('created_at', 'id'))
    if not pages:
        raise Http404
    from PIL import Image
    pdf_images = []
    for page in pages:
        page = ensure_archive_image(page)
        page.processed_image.open('rb')
        try:
            with Image.open(page.processed_image) as image:
                pdf_images.append(image.convert('RGB').copy())
        finally:
            page.processed_image.close()
    output = io.BytesIO()
    pdf_images[0].save(
        output, format='PDF', save_all=True, append_images=pdf_images[1:],
        resolution=150.0, title=notebook.title,
    )
    output.seek(0)
    response = FileResponse(output, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="course-notebook-{notebook.id}.pdf"'
    return response


@login_required
@require_POST
def course_notebook_page_archive_process(request, page_id):
    """OCR 비용 없이 현재 사진만 A4 문서 이미지로 보정한다."""
    page = ensure_archive_image(_student_notebook_page(request.user, page_id))
    return JsonResponse({
        'message': 'A4 문서 보정이 완료되었습니다.',
        'processed_image_url': page.processed_image.url,
    })


@login_required
@require_POST
def course_notebook_page_process(request, page_id):
    """원본을 보정하고 설정된 OCR 제공자로 텍스트를 한 번 추출한다."""
    page = _student_notebook_page(request.user, page_id)
    if (
        page.ocr_status == CourseNotebookPage.OcrStatus.PROCESSING
        and page.ocr_processed_at
        and page.ocr_processed_at > timezone.now() - timedelta(minutes=5)
    ):
        return JsonResponse({'message': '이미 변환 중입니다.'}, status=409)
    page = process_course_notebook_page(page)
    payload = {
        'status': page.ocr_status,
        'status_label': page.get_ocr_status_display(),
        'text': page.ocr_corrected_text or page.ocr_raw_text,
        'error': page.ocr_error,
        'processed_image_url': page.processed_image.url if page.processed_image else '',
        'provider': page.ocr_provider,
    }
    if page.ocr_status == CourseNotebookPage.OcrStatus.FAILED:
        payload['message'] = page.ocr_error or '이미지 처리에 실패했습니다.'
        return JsonResponse(payload, status=422)
    payload['message'] = '이미지 보정과 텍스트 변환이 완료되었습니다.'
    return JsonResponse(payload)


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
