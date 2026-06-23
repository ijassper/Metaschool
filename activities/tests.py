from types import SimpleNamespace
from pathlib import Path

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.template.loader import get_template
from django.urls import reverse
from django.conf import settings

from .views.exam_views import pdf_viewer


@override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage'
)
class PdfViewerTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True)

    def test_pdf_viewer_accepts_same_origin_media_path(self):
        request = self.factory.get(
            reverse('pdf_viewer'),
            {'file': '/media/activity_files/reference.pdf'},
        )
        request.user = self.user

        response = pdf_viewer(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/media/activity_files/reference.pdf')

    def test_pdf_viewer_rejects_external_url(self):
        request = self.factory.get(
            reverse('pdf_viewer'),
            {'file': 'https://example.com/reference.pdf'},
        )
        request.user = self.user

        response = pdf_viewer(request)

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            '올바른 PDF 파일 경로가 아닙니다.',
            status_code=400,
        )

    def test_pdf_viewer_rejects_path_traversal(self):
        request = self.factory.get(
            reverse('pdf_viewer'),
            {'file': '/media/../private/reference.pdf'},
        )
        request.user = self.user

        response = pdf_viewer(request)

        self.assertEqual(response.status_code, 400)

    def test_exam_and_pdf_viewer_templates_compile(self):
        self.assertIsNotNone(get_template('activities/take_test.html'))
        self.assertIsNotNone(get_template('activities/pdf_viewer.html'))

    def test_pdf_controls_are_non_submitting_and_stop_event_propagation(self):
        template_source = get_template(
            'activities/pdf_viewer.html'
        ).template.source

        self.assertIn('class="modal-button"', template_source)
        self.assertIn('tabindex="-1"', template_source)
        self.assertIn('event.preventDefault()', template_source)
        self.assertIn('event.stopPropagation()', template_source)
        self.assertNotIn('location.reload', template_source)
        self.assertNotIn('window.location.href =', template_source)

    def test_exam_security_ignores_only_active_pdf_modal_focus(self):
        template_source = get_template(
            'activities/take_test.html'
        ).template.source

        self.assertIn('let is_modal_active = false', template_source)
        self.assertIn('isPdfModalInteractionActive()', template_source)
        self.assertIn("event.data.type === 'pdf-viewer-interaction'", template_source)

    def test_pdf_modal_supports_drag_resize_minimize_and_reset(self):
        template_source = get_template(
            'activities/take_test.html'
        ).template.source

        self.assertIn('class="modal-dialog resizable-modal"', template_source)
        self.assertIn('id="filePreviewDragHandle"', template_source)
        self.assertIn('id="filePreviewResizeHandle"', template_source)
        self.assertIn("addEventListener('pointerdown'", template_source)
        self.assertIn("setPointerCapture(event.pointerId)", template_source)
        self.assertIn("addEventListener('touchstart'", template_source)
        self.assertIn("addEventListener('touchmove'", template_source)
        self.assertIn("addEventListener('touchend'", template_source)
        self.assertIn('function constrainPreviewRect', template_source)
        self.assertIn('function togglePreviewMinimize', template_source)
        self.assertIn('function resetPreviewDialog', template_source)
        self.assertIn("width: min(40vw, 640px)", template_source)
        self.assertIn('min-width: 300px', template_source)
        self.assertIn('min-height: 200px', template_source)

    def test_exam_start_labels_and_fullscreen_navigation_are_standardized(self):
        template_root = Path(settings.BASE_DIR) / 'templates'
        combined_templates = '\n'.join(
            path.read_text(encoding='utf-8')
            for path in template_root.rglob('*.html')
        )
        take_test_source = get_template(
            'activities/take_test.html'
        ).template.source
        dashboard_source = get_template(
            'activities/student_dashboard.html'
        ).template.source

        self.assertNotIn('전체 화면으로 복귀하여 응시 계속하기', combined_templates)
        self.assertNotIn('응시 시작하기', combined_templates)
        self.assertIn('id="start-btn"', take_test_source)
        self.assertIn('async function startTest(event)', take_test_source)
        self.assertIn('await requestExamFullscreen()', take_test_source)
        self.assertIn('let isStartingExam = false', take_test_source)
        self.assertIn(
            'isSubmitting || isStartingExam || IS_DEMO',
            take_test_source,
        )
        self.assertNotIn('const wasStarted = testStarted', take_test_source)
        self.assertIn(
            'await document.documentElement.requestFullscreen()',
            dashboard_source,
        )
        self.assertIn('window.location.href = card.dataset.href', dashboard_source)
