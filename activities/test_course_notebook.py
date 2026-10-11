from django.template.loader import get_template
from django.test import RequestFactory
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from types import SimpleNamespace
from unittest.mock import patch
import json

from .models import (
    Activity, CourseNotebook, CourseNotebookMaterial, CourseNotebookPage,
    CourseNotebookSection, CourseNotebookStickyNote,
)
from .views.course_notebook_views import parse_section_outline
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
        self.assertIn('새 교과 수업 노트', list_source)
        self.assertIn('대상 학생', form_source)
        first_row_labels = [form_source.index(label) for label in ['학년도', '학기', '과목명', '노트 제목']]
        self.assertEqual(first_row_labels, sorted(first_row_labels))
        self.assertIn('name="title" maxlength="30"', form_source)
        self.assertIn("value == 'YEAR'", form_source)
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
        self.assertIn('노트 사진 저장', student_source)
        self.assertIn('포스트잇 편집', student_source)
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
        self.assertEqual(CourseNotebookSection._meta.get_field('title').max_length, 100)
        self.assertEqual(CourseNotebookMaterial._meta.get_field('original_name').max_length, 255)
        self.assertEqual(CourseNotebookStickyNote._meta.get_field('content').max_length, 1000)
        for heading in ['학년도', '학기', '과목명', '노트 제목', '상태', '학생 현황']:
            self.assertIn(f'<th>{heading}</th>', list_source)

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

    def test_student_selector_restores_last_completed_selection(self):
        modal_source = get_template('components/student_modal_core.html').template.source
        form_source = get_template('activities/unified_form.html').template.source
        self.assertIn('committedSelectedStudentIds', modal_source)
        self.assertIn('restoreCommittedStudentSelection()', modal_source)
        self.assertNotIn('const currentTargets = {{ current_targets|safe }}', modal_source)
        self.assertIn("form_data.selected_students_json|default:''", form_source)
