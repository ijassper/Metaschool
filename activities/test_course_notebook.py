from django.template.loader import get_template
from django.test import RequestFactory
from django.test import SimpleTestCase, TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
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
    def test_last_level_sections_are_horizontal_even_directly_under_a_chapter(self):
        leaf_nodes = [
            {
                'section': SimpleNamespace(depth=1, title=title),
                'total_count': 0, 'own_count': 0, 'children': [],
            }
            for title in ['가. 시의 표현과 감상', '나. 소설의 인물과 사건 이해하기']
        ]
        chapter = {
            'section': SimpleNamespace(depth=0, title='1. 문학과 나의 삶'),
            'total_count': 0, 'own_count': 0, 'children': leaf_nodes,
            'all_leaf_children': True,
        }

        html = get_template('activities/course_notebook_section_tree_nodes.html').render(
            {'nodes': [chapter]},
        )

        self.assertIn('class="tree-children is-leaf-row"', html)
        self.assertIn('가. 시의 표현과 감상', html)
        self.assertIn('나. 소설의 인물과 사건 이해하기', html)

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
        section_source = get_template('activities/student_course_notebook_section.html').template.source
        page_source = get_template('activities/student_course_notebook_page.html').template.source
        submission_source = get_template('activities/course_notebook_submission_status.html').template.source
        student_status_source = get_template('activities/course_notebook_student_status.html').template.source
        teacher_page_source = get_template('activities/course_notebook_teacher_page.html').template.source
        tree_source = get_template('activities/course_notebook_section_tree_nodes.html').template.source
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
        self.assertIn('내 노트 한눈에 보기', student_source)
        self.assertIn('section_items', student_source)
        self.assertIn('?section={{ item.section.id }}', student_source)
        self.assertIn('toc-page-strip', student_source)
        self.assertIn('단원 펼쳐보기', student_source)
        self.assertIn('노트 추가하기', student_source)
        self.assertIn('#sectionNotes', student_source)
        self.assertIn('#noteCaptureCard', student_source)
        self.assertIn('aspect-ratio:210/297', student_source)
        self.assertLess(
            student_source.index('<span class="toc-page-title">'),
            student_source.index('<span class="toc-page-image">'),
        )
        self.assertIn('이전에 올린 미분류 노트', student_source)
        self.assertNotIn('name="section"', section_source)
        self.assertIn('노트 페이지 제목', section_source)
        self.assertIn('노트 촬영', section_source)
        self.assertIn('노트 업로드', section_source)
        self.assertIn('capture="environment"', section_source)
        self.assertIn('id="sectionNotes"', section_source)
        self.assertIn('aspect-ratio:210/297', section_source)
        self.assertLess(
            section_source.index('<span class="section-page-title">'),
            section_source.index('<span class="section-page-image">'),
        )
        self.assertIn('id="nativeDocumentScan"', section_source)
        self.assertIn('id="photoReview"', section_source)
        self.assertIn('id="photoThumbnails"', section_source)
        self.assertIn('id="retakeNotePhoto"', section_source)
        self.assertIn('다시 촬영·선택', section_source)
        self.assertIn('선택한 사진 제출', section_source)
        self.assertIn("form.addEventListener('submit'", section_source)
        self.assertIn("'student_course_notebook_page' page.id", section_source)
        self.assertNotIn('pageEditorModal', section_source)
        self.assertIn('전체 PDF 다운로드', page_source)
        self.assertIn('archive-current', page_source)
        self.assertIn('previous_page', page_source)
        self.assertIn('next_page', page_source)
        self.assertIn('id="continueUploadModal"', page_source)
        self.assertIn('다음 페이지도 계속 제출할까요?', page_source)
        self.assertIn('다음 페이지 계속 촬영', page_source)
        self.assertIn('upload-choice-actions', page_source)
        self.assertIn('제출 완료', page_source)
        self.assertIn('id="zoomReset"', page_source)
        self.assertIn("searchParams.delete('uploaded')", page_source)
        self.assertIn('id="noteCaptureCard"', section_source)
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
        for heading in ['학년도', '학기', '과목명', '노트 제목', '상태', '학생 현황', '관리 도구']:
            self.assertIn(f'<th>{heading}</th>', list_source)
        self.assertIn("{% url 'course_notebook_submission_status' notebook.id %}", list_source)
        self.assertIn('제출 현황', list_source)
        for label in ['대상 학생', '작성 학생', '미작성 학생', '전체 노트']:
            self.assertIn(label, submission_source)
        self.assertIn('name="grade"', submission_source)
        self.assertIn('name="class_no"', submission_source)
        self.assertIn('name="status"', submission_source)
        self.assertIn('name="q"', submission_source)
        self.assertIn("{% url 'course_notebook_student_status' notebook.id row.student.id %}", submission_source)
        self.assertIn("{% url 'course_notebook_teacher_page' notebook.id student.id page.id %}", student_status_source)
        self.assertIn("{% url 'course_notebook_teacher_pdf' notebook.id student.id %}", student_status_source)
        self.assertIn('reader-stage', teacher_page_source)
        for heading in ['학년', '반', '번호', '이름', '상태', '최근 작성일', '전체 장수', '단원별 장수']:
            self.assertIn(f'<th>{heading}</th>', submission_source)
        self.assertIn('border-bottom:1px solid #f0ebf2;vertical-align:top', submission_source)
        self.assertIn('.tree-children.is-leaf-row{display:flex;flex-wrap:wrap', submission_source)
        self.assertIn('{% if node.all_leaf_children %} is-leaf-row{% endif %}', tree_source)
        self.assertIn('min-width:30%;max-width:100%', submission_source)
        self.assertIn('제출 현황으로', student_status_source)
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


class CourseNotebookSubmissionStatusTests(TestCase):
    def setUp(self):
        self.teacher = CustomUser.objects.create_user(
            username='status-teacher@example.com', email='status-teacher@example.com',
            password='test-password', name='담당 교사', role=CustomUser.Role.TEACHER,
            is_approved=True,
        )
        self.other_teacher = CustomUser.objects.create_user(
            username='status-other@example.com', email='status-other@example.com',
            password='test-password', name='다른 교사', role=CustomUser.Role.TEACHER,
            is_approved=True,
        )
        self.submitted_student = Student.objects.create(
            teacher=self.teacher, grade=2, class_no=6, number=1, name='김작성',
        )
        self.empty_student = Student.objects.create(
            teacher=self.teacher, grade=2, class_no=7, number=2, name='이미작성',
        )
        self.notebook = CourseNotebook.objects.create(
            teacher=self.teacher, title='국어 필기노트', subject='국어', academic_year=2026,
            semester=CourseNotebook.Semester.FIRST, cover_color='PURPLE',
        )
        self.notebook.target_students.add(self.submitted_student, self.empty_student)
        self.section = CourseNotebookSection.objects.create(
            notebook=self.notebook, title='문학과 나의 삶', depth=0, position=0,
        )
        CourseNotebookPage.objects.create(
            notebook=self.notebook, student=self.submitted_student, section=self.section,
            image=SimpleUploadedFile('note.jpg', b'note-image', content_type='image/jpeg'),
        )
        self.client.force_login(self.teacher)

    def test_submission_status_summarizes_and_filters_students(self):
        response = self.client.get(
            reverse('course_notebook_submission_status', args=[self.notebook.id]),
            {'status': 'not_submitted', 'class_no': '7'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['total_students'], 2)
        self.assertEqual(response.context['summary']['submitted_students'], 1)
        self.assertEqual(len(response.context['student_rows']), 1)
        self.assertEqual(response.context['student_rows'][0]['student'], self.empty_student)

    def test_section_tree_expands_inside_the_student_row_cell(self):
        response = self.client.get(reverse(
            'course_notebook_submission_status', args=[self.notebook.id],
        ))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        section_cell = html.split('<td class="section-cell">', 1)[1].split('</td>', 1)[0]
        self.assertIn('장수 보기', section_cell)
        self.assertIn('class="section-tree"', section_cell)
        self.assertIn('문학과 나의 삶', section_cell)
        self.assertNotIn('class="section-breakdown"', html)

    def test_teacher_can_open_target_students_note_view(self):
        response = self.client.get(reverse(
            'course_notebook_student_status',
            args=[self.notebook.id, self.submitted_student.id],
        ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_page_count'], 1)
        self.assertContains(response, '김작성 학생의 수업 노트')

    def test_other_teacher_cannot_open_submission_status(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(reverse(
            'course_notebook_submission_status', args=[self.notebook.id],
        ))

        self.assertEqual(response.status_code, 404)

    def test_teacher_reader_stays_within_the_current_section(self):
        other_section = CourseNotebookSection.objects.create(
            notebook=self.notebook, title='생각을 나누는 대화', depth=0, position=1,
        )
        current_page = CourseNotebookPage.objects.get(student=self.submitted_student)
        CourseNotebookPage.objects.create(
            notebook=self.notebook, student=self.submitted_student,
            section=other_section, image='course_notebooks/other.jpg',
        )

        response = self.client.get(reverse('course_notebook_teacher_page', args=[
            self.notebook.id, self.submitted_student.id, current_page.id,
        ]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['pages']), 1)
        self.assertIsNone(response.context['next_page'])

    def test_teacher_pdf_includes_descendant_pages_and_checks_ownership(self):
        child = CourseNotebookSection.objects.create(
            notebook=self.notebook, parent=self.section,
            title='시의 표현과 감상', depth=1, position=1,
        )
        CourseNotebookPage.objects.create(
            notebook=self.notebook, student=self.submitted_student,
            section=child, image='course_notebooks/child.jpg',
        )
        from django.http import HttpResponse
        url = reverse('course_notebook_teacher_pdf', args=[
            self.notebook.id, self.submitted_student.id,
        ])
        with patch('activities.views.course_notebook_views._course_notebook_pdf_response',
                   return_value=HttpResponse('pdf')) as pdf_response:
            response = self.client.get(url, {'section': self.section.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(pdf_response.call_args.args[0]), 2)

        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_submission_tree_rolls_child_pages_into_parent_count(self):
        child = CourseNotebookSection.objects.create(
            notebook=self.notebook, parent=self.section,
            title='시의 표현과 감상', depth=1, position=1,
        )
        CourseNotebookPage.objects.create(
            notebook=self.notebook, student=self.submitted_student,
            section=child, image='course_notebooks/child.jpg',
        )

        response = self.client.get(reverse(
            'course_notebook_submission_status', args=[self.notebook.id],
        ))

        tree = response.context['student_rows'][0]['section_tree']
        self.assertEqual(tree[0]['total_count'], 2)
        self.assertEqual(tree[0]['children'][0]['total_count'], 1)
        self.assertContains(response, '시의 표현과 감상')


class CourseNotebookStudentUploadTests(TestCase):
    def setUp(self):
        self.teacher = CustomUser.objects.create_user(
            username='upload-teacher@example.com', email='upload-teacher@example.com',
            password='test-password', name='담당 교사', role=CustomUser.Role.TEACHER,
            is_approved=True,
        )
        self.student_user = CustomUser.objects.create_user(
            username='student-upload', email='student-upload@example.com',
            password='test-password', name='김학생', role=CustomUser.Role.STUDENT,
            is_approved=True,
        )
        self.student = Student.objects.create(
            teacher=self.teacher, grade=2, class_no=6, number=1,
            name='김학생', email=self.student_user.email,
        )
        self.notebook = CourseNotebook.objects.create(
            teacher=self.teacher, title='한국사 노트', subject='한국사', academic_year=2026,
            semester=CourseNotebook.Semester.YEAR, description='수업 노트', cover_color='PURPLE',
        )
        self.notebook.target_students.add(self.student)
        self.section = CourseNotebookSection.objects.create(
            notebook=self.notebook, title='고조선', depth=0, position=0,
        )
        self.client.force_login(self.student_user)

    def test_upload_requires_section_when_notebook_has_sections(self):
        upload = SimpleUploadedFile('note.jpg', b'not-an-image', content_type='image/jpeg')

        response = self.client.post(
            reverse('student_course_notebook', args=[self.notebook.id]),
            {'image': upload, 'memo': '첫 페이지'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '목차에서 노트를 저장할 단원을 선택해 주세요.')
        self.assertEqual(CourseNotebookPage.objects.count(), 0)

    def test_student_reader_navigation_is_limited_to_one_section(self):
        other_section = CourseNotebookSection.objects.create(
            notebook=self.notebook, title='다른 단원', depth=0, position=1,
        )
        first = CourseNotebookPage.objects.create(
            notebook=self.notebook, student=self.student, section=self.section,
            image='course_notebooks/first.jpg',
        )
        second = CourseNotebookPage.objects.create(
            notebook=self.notebook, student=self.student, section=other_section,
            image='course_notebooks/second.jpg',
        )

        response = self.client.get(reverse('student_course_notebook_page', args=[first.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([page.id for page in response.context['archive_pages']], [first.id])
        self.assertEqual(response.context['page_count'], 1)
        self.assertIsNone(response.context['next_page'])
        self.assertNotContains(response, reverse('student_course_notebook_page', args=[second.id]))
