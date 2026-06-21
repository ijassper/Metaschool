from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.template.loader import get_template
from django.urls import reverse

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
