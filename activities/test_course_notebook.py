from django.template.loader import get_template
from django.test import RequestFactory
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from types import SimpleNamespace
from unittest.mock import patch
import json

from .models import Activity, CourseNotebook, CourseNotebookPage
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
        self.assertNotIn('대단원과 소단원은 다음 화면에서 구성합니다', form_source)
        self.assertIn('capture="environment"', student_source)
        self.assertIn('노트 사진 저장', student_source)
        self.assertEqual(CourseNotebook.Semester.FIRST, '1')
        self.assertEqual(CourseNotebookPage._meta.get_field('memo').max_length, 200)

    def test_course_notebook_sidebar_uses_mega_menu_metadata(self):
        source = get_template('base.html').template.source
        self.assertIn('data-mega-category="COURSE_NOTEBOOK"', source)
        self.assertIn('link.dataset.megaCategory', source)

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
