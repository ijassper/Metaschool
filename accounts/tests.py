from pathlib import Path
import inspect
import re
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from .middleware import StudentSessionValidationMiddleware
from .views import login_view


class CsrfAndSessionConsistencyTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_csrf_cookie_is_available_to_common_fetch_wrapper(self):
        self.assertFalse(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.LOGIN_URL, '/accounts/login/')
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

        script = (
            Path(settings.BASE_DIR)
            / 'static'
            / 'js'
            / 'ingrid-fetch.js'
        ).read_text(encoding='utf-8')
        self.assertIn("getCookie('csrftoken')", script)
        self.assertIn("headers.set('X-CSRFToken', csrfToken)", script)
        self.assertIn("'X-Session-Expired'", script)

    def test_replaced_student_ajax_session_returns_identifiable_401(self):
        request = self.factory.post(
            '/accounts/dashboard/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_student=True,
            pk=7,
            current_session_key='new-session',
        )
        request.session = SimpleNamespace(session_key='old-session')
        middleware = StudentSessionValidationMiddleware(
            lambda req: HttpResponse('unreachable')
        )

        with patch('accounts.middleware.logout'):
            response = middleware(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response['X-Session-Expired'], '1')
        self.assertIn('no-store', response['Cache-Control'])

    def test_login_page_is_not_cached(self):
        request = self.factory.get('/accounts/login/')
        request.user = AnonymousUser()
        middleware = StudentSessionValidationMiddleware(
            lambda req: HttpResponse('login')
        )

        response = middleware(request)

        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('private', response['Cache-Control'])

    def test_authenticated_dashboard_is_not_cached(self):
        request = self.factory.get('/accounts/dashboard/')
        request.user = SimpleNamespace(
            is_authenticated=True,
            is_student=False,
        )
        middleware = StudentSessionValidationMiddleware(
            lambda req: HttpResponse('dashboard')
        )

        response = middleware(request)

        self.assertIn('no-store', response['Cache-Control'])

    def test_login_rotates_session_and_csrf_tokens(self):
        source = inspect.getsource(login_view)

        self.assertIn('request.session.cycle_key()', source)
        self.assertIn('rotate_token(request)', source)
        self.assertIn('select_for_update()', source)

    def test_all_post_forms_include_csrf_token(self):
        template_root = Path(settings.BASE_DIR) / 'templates'
        missing = []

        for path in template_root.rglob('*.html'):
            source = path.read_text(encoding='utf-8')
            for form in re.finditer(
                r'<form\b[^>]*\bmethod\s*=\s*["\']post["\'][^>]*>',
                source,
                re.IGNORECASE | re.DOTALL,
            ):
                end = source.find('</form>', form.end())
                form_source = source[form.start():end if end >= 0 else form.end()]
                if '{% csrf_token %}' not in form_source:
                    missing.append(f'{path}:{source.count(chr(10), 0, form.start()) + 1}')

        self.assertEqual(missing, [])
