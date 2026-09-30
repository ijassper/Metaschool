from django.template.loader import get_template
from django.test import SimpleTestCase

from .models import Activity, CourseNotebook, CourseNotebookPage
from .views.main_views import get_form_config


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
