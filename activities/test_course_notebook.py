from django.template.loader import get_template
from django.test import RequestFactory
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from types import SimpleNamespace
from unittest.mock import patch
import json
import io

from PIL import Image

from accounts.models import CustomUser, Student

from .models import (
    Activity, CourseNotebook, CourseNotebookMaterial, CourseNotebookPage,
    CourseNotebookSection, CourseNotebookStickyNote,
)
from .views.course_notebook_views import parse_section_outline
from .course_notebook_processing import correct_notebook_image
from .views.main_views import get_form_config, get_menu_items


class CourseNotebookUiTests(SimpleTestCase):
    def test_legacy_scratchpad_is_renamed_in_current_ui(self):
        self.assertTrue(Activity(sub_category='다목적 연습장').is_notebook)
        self.assertTrue(Activity(sub_category='수업 노트/연습장').is_notebook)
        self.assertTrue(get_form_config('다목적 연습장')['show_notebook'])

    def test_sidebar_orders_requested_note_menus(self):
        source = get_template('base.html').template.source
        practical = source.index('실기활동 보고서</a>')
        course = source.index('교과 수업 노트</a>')
        scratchpad = source.index('다목적 연습장</a>')
        self.assertLess(practical, course)
        self.assertLess(course, scratchpad)

    def test_course_notebook_templates_compile(self):
        list_source = get_template('activities/course_notebook_list.html').template.source
        form_source = get_template('activities/course_notebook_form.html').template.source
        student_source = get_template('activities/student_course_notebook.html').template.source
        page_source = get_template('activities/student_course_notebook_page.html').template.source
        self.assertIn('새 교과 수업 노트', list_source)
        self.assertIn('btn btn-course-note-primary rounded-pill px-4 fw-bold', list_source)
        self.assertIn('background:var(--ingrid-gradient', list_source)
        self.assertIn('대상 학생', form_source)
        first_row_labels = [form_source.index(label) for label in ['학년도', '학기', '과목명', '노트 제목']]
        self.assertEqual(first_row_labels, sorted(first_row_labels))
        self.assertIn('name="title" maxlength="30"', form_source)
        self.assertIn('form_values.semester == value', form_source)
        self.assertIn('노트 소개', form_source)
        self.assertNotIn('>학생 안내<', form_source)
        self.assertIn('courseNotebookStudentModal', form_source)
        self.assertIn('grid-template-rows:repeat(5', form_source)
        self.assertIn('grid-template-columns:repeat(8', form_source)
        self.assertIn('grid-auto-flow:column', form_source)
        self.assertIn('data-student-search=', form_source)
        self.assertIn("tokens.every", form_source)
        self.assertIn('id="studentGradeFilter"', form_source)
        self.assertIn('id="studentClassFilter"', form_source)
        self.assertIn('id="toggleGradeStudents"', form_source)
        self.assertIn('toggle-class-students', form_source)
        self.assertIn('전교생 전체 선택', form_source)
        self.assertIn('data-grade=', form_source)
        self.assertIn('>단원 구조<', form_source)
        self.assertNotIn('name="enable_outline"', form_source)
        self.assertIn('name="materials"', form_source)
        self.assertNotIn('대단원과 소단원은 다음 화면에서 구성합니다', form_source)
        self.assertIn('capture="environment"', student_source)
        self.assertIn('id="nativeDocumentScan"', student_source)
        self.assertIn('노트 사진 아카이브에 추가', student_source)
        self.assertIn('multiple required', student_source)
        self.assertIn('아카이브 열기', student_source)
        self.assertIn("'student_course_notebook_page' page.id", student_source)
        self.assertNotIn('pageEditorModal', student_source)
        self.assertIn('전체 PDF 다운로드', page_source)
        self.assertIn('archive-current', page_source)
        self.assertIn('previous_page', page_source)
        self.assertIn('next_page', page_source)
        self.assertIn("'course_notebook_page_archive_process' page.id", page_source)
        self.assertEqual(CourseNotebook.Semester.FIRST, '1')
        self.assertEqual(CourseNotebook.Semester.YEAR.label, '전학기')
        self.assertEqual(CourseNotebook._meta.get_field('semester').default, CourseNotebook.Semester.YEAR)
        self.assertEqual(
            [value for value, _ in CourseNotebook.COVER_COLOR_CHOICES],
            ['PURPLE', 'BLUE', 'GREEN', 'YELLOW', 'ORANGE', 'RED', 'PINK', 'LIME'],
        )
        for color in ['YELLOW', 'RED', 'LIME']:
            self.assertIn(f'.cover-option .{color}', form_source)
        self.assertEqual(CourseNotebookPage._meta.get_field('memo').max_length, 200)
        self.assertEqual(CourseNotebookPage._meta.get_field('ocr_status').default, 'UPLOADED')
        self.assertEqual(CourseNotebookPage._meta.get_field('ocr_layout').default, dict)
        self.assertEqual(CourseNotebookPage._meta.get_field('ocr_usage').default, dict)
        page = CourseNotebookPage(ocr_raw_text='자동 인식', ocr_corrected_text='학생 확인')
        self.assertEqual(page.analysis_text, '학생 확인')
        self.assertEqual(CourseNotebookSection._meta.get_field('title').max_length, 100)
        self.assertEqual(CourseNotebookMaterial._meta.get_field('original_name').max_length, 255)
        self.assertEqual(CourseNotebookStickyNote._meta.get_field('content').max_length, 1000)
        for heading in ['학년도', '학기', '과목명', '노트 제목', '상태', '학생 현황']:
            self.assertIn(f'<th>{heading}</th>', list_source)
        self.assertIn("{% url 'course_notebook_update' notebook.id %}", list_source)
        self.assertIn('교과 수업 노트 수정', form_source)
        self.assertIn('수정 완료', form_source)
        self.assertIn('name="delete_materials"', form_source)
        self.assertIn('bi-arrow-left me-1"></i>목록으로', form_source)
        self.assertIn('btn btn-ingrid-primary rounded-pill px-4 fw-bold', form_source)
        self.assertIn('background:var(--ingrid-gradient', form_source)

    def test_notebook_image_correction_keeps_color_and_limits_size(self):
        source = Image.new('RGB', (3000, 1800), (245, 235, 180))
        buffer = io.BytesIO()
        source.save(buffer, format='JPEG')
        corrected = Image.open(io.BytesIO(correct_notebook_image(buffer.getvalue())))
        self.assertEqual(corrected.mode, 'RGB')
        self.assertEqual(corrected.size, (1240, 1754))
        self.assertEqual(corrected.format, 'JPEG')

    def test_section_outline_supports_markdown_and_indentation(self):
        outline = '# 1. 고조선\n  - 청동기 시대\n    고조선의 건국\n# 2. 삼국 시대'
        self.assertEqual(parse_section_outline(outline), [
            {'title': '1. 고조선', 'depth': 0},
            {'title': '청동기 시대', 'depth': 1},
            {'title': '고조선의 건국', 'depth': 2},
            {'title': '2. 삼국 시대', 'depth': 0},
        ])

    def test_section_outline_limits_depth_jumps(self):
        self.assertEqual(parse_section_outline('첫 단원\n          끊어진 하위 단원')[1]['depth'], 1)

    def test_section_outline_supports_seven_heading_levels(self):
        outline = '\n'.join('#' * depth + f' {depth}단계' for depth in range(1, 8))
        parsed = parse_section_outline(outline)
        self.assertEqual([item['depth'] for item in parsed], list(range(7)))
        form_source = get_template('activities/course_notebook_form.html').template.source
        self.assertIn('####### 소소소소소단원', form_source)
        self.assertIn('최대 7단계', form_source)

    def test_course_notebook_sidebar_uses_mega_menu_metadata(self):
        source = get_template('base.html').template.source
        self.assertIn('data-mega-category="COURSE_NOTEBOOK"', source)
        self.assertIn('link.dataset.megaCategory', source)

    def test_dashboard_uses_eight_unique_pastel_colors(self):
        teacher_source = get_template('dashboard.html').template.source
        student_source = get_template('activities/student_dashboard.html').template.source
        expected_cycle = "'pastel-purple' 'pastel-blue' 'pastel-green' 'pastel-yellow' 'pastel-orange' 'pastel-red' 'pastel-pink' 'pastel-lime'"
        self.assertIn(expected_cycle, teacher_source)
        self.assertIn(expected_cycle, student_source)
        self.assertIn('.pastel-lime', teacher_source)
        self.assertIn('.pastel-lime', student_source)

    def test_course_notebook_mega_menu_returns_teacher_notebooks(self):
        request = RequestFactory().get('/activities/get-menu-items/', {
            'category': 'COURSE_NOTEBOOK',
            'sub': '교과 수업 노트',
        })
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_approved=True,
            role='TEACHER',
        )
        notebook = SimpleNamespace(
            id=31,
            title='우리 반 역사 노트',
            subject='역사',
            updated_at=timezone.now(),
            target_students=SimpleNamespace(count=lambda: 25),
        )
        with patch('activities.views.main_views.CourseNotebook.objects') as manager:
            manager.filter.return_value.prefetch_related.return_value.order_by.return_value = [notebook]
            response = get_menu_items(request)

        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['items'][0]['activity_name'], '우리 반 역사 노트')
        self.assertEqual(payload['items'][0]['detail_topic'], '역사 · 대상 학생 25명')
        self.assertEqual(payload['items'][0]['url'], f"{reverse('course_notebook_list')}#course-notebook-31")

    def test_student_dashboard_compacts_welcome_card_on_tablets(self):
        source = get_template('activities/student_dashboard.html').template.source
        self.assertIn('(min-width: 769px) and (max-width: 1366px) and (pointer: coarse)', source)
        self.assertIn('student-dashboard-shell', source)
        self.assertIn('padding: 14px 24px', source)

    def test_student_dashboard_course_notebook_cards_show_learning_status(self):
        source = get_template('activities/student_dashboard.html').template.source
        self.assertIn('student-note-status', source)
        self.assertIn('내 노트 {{ notebook.my_page_count }}장', source)
        self.assertIn('단원 {{ notebook.section_count }}', source)
        self.assertIn('교재 {{ notebook.material_count }}', source)
        self.assertIn('{{ notebook.teacher.name }} 선생님', source)
        self.assertIn("{% url 'student_course_notebook' notebook.id %}", source)
        self.assertIn('{% if block.course_notebooks %}', source)
        self.assertNotIn('class="student-note-section"', source)

    def test_student_selector_restores_last_completed_selection(self):
        modal_source = get_template('components/student_modal_core.html').template.source
        form_source = get_template('activities/unified_form.html').template.source
        self.assertIn('committedSelectedStudentIds', modal_source)
        self.assertIn('restoreCommittedStudentSelection()', modal_source)
        self.assertNotIn('const currentTargets = {{ current_targets|safe }}', modal_source)
        self.assertIn("form_data.selected_students_json|default:''", form_source)


class CourseNotebookUpdateTests(TestCase):
    def setUp(self):
        self.teacher = CustomUser.objects.create_user(
            username='teacher@example.com', email='teacher@example.com', password='test-password',
            name='담당 교사', role=CustomUser.Role.TEACHER, is_approved=True,
        )
        self.other_teacher = CustomUser.objects.create_user(
            username='other@example.com', email='other@example.com', password='test-password',
            name='다른 교사', role=CustomUser.Role.TEACHER, is_approved=True,
        )
        self.student = Student.objects.create(
            teacher=self.teacher, grade=2, class_no=6, number=1, name='김학생',
        )
        self.notebook = CourseNotebook.objects.create(
            teacher=self.teacher, title='기존 노트', subject='국어', academic_year=2026,
            semester=CourseNotebook.Semester.YEAR, description='기존 소개', cover_color='PURPLE',
        )
        self.notebook.target_students.add(self.student)
        self.first_section = CourseNotebookSection.objects.create(
            notebook=self.notebook, title='기존 대단원', depth=0, position=0,
        )
        CourseNotebookSection.objects.create(
            notebook=self.notebook, parent=self.first_section, title='기존 소단원', depth=1, position=1,
        )
        self.client.force_login(self.teacher)

    def test_update_page_prepopulates_notebook(self):
        response = self.client.get(reverse('course_notebook_update', args=[self.notebook.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '교과 수업 노트 수정')
        self.assertContains(response, 'value="기존 노트"')
        self.assertContains(response, '# 기존 대단원')
        self.assertContains(response, '## 기존 소단원')
        self.assertContains(response, f'value="{self.student.id}" checked')

    def test_owner_can_update_notebook_and_outline(self):
        response = self.client.post(reverse('course_notebook_update', args=[self.notebook.id]), {
            'academic_year': '2026',
            'semester': CourseNotebook.Semester.FIRST,
            'subject': '역사',
            'title': '수정된 노트',
            'description': '수정된 소개',
            'cover_color': 'LIME',
            'target_students': [str(self.student.id)],
            'section_outline': '# 새 대단원\n## 새 소단원\n### 새 세부단원',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"{reverse('course_notebook_list')}#course-notebook-{self.notebook.id}",
        )
        self.notebook.refresh_from_db()
        self.assertEqual(self.notebook.title, '수정된 노트')
        self.assertEqual(self.notebook.subject, '역사')
        self.assertEqual(self.notebook.semester, CourseNotebook.Semester.FIRST)
        self.assertEqual(self.notebook.cover_color, 'LIME')
        sections = list(self.notebook.sections.order_by('position'))
        self.assertEqual([section.title for section in sections], ['새 대단원', '새 소단원', '새 세부단원'])
        self.assertEqual(sections[0].id, self.first_section.id)
        self.assertEqual(sections[1].parent_id, sections[0].id)
        self.assertEqual(sections[2].parent_id, sections[1].id)

    def test_teacher_cannot_edit_another_teachers_notebook(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(reverse('course_notebook_update', args=[self.notebook.id]))

        self.assertEqual(response.status_code, 404)
