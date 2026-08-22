from pathlib import Path
import inspect
import re
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse
from django.template.loader import get_template

from .middleware import StudentSessionValidationMiddleware
from .views import admin_system_settings, login_view, persona_create


class AdminSystemSettingsPersonaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_persona_routes_are_owned_by_accounts_system_settings(self):
        self.assertIs(resolve(reverse('persona_create')).func, persona_create)
        self.assertTrue(reverse('persona_create').startswith('/accounts/system-settings/personas/'))

    def test_non_admin_cannot_access_system_settings(self):
        request = self.factory.get(reverse('admin_system_settings'))
        request.user = SimpleNamespace(is_authenticated=True, role='TEACHER')
        request._messages = SimpleNamespace(add=lambda *args, **kwargs: None)
        with patch('accounts.views.messages.error'):
            response = admin_system_settings(request)
        self.assertEqual(302, response.status_code)
        self.assertEqual(reverse('dashboard'), response.url)

    def test_system_settings_has_three_admin_tabs_and_persona_crud(self):
        source = get_template('accounts/system_settings.html').template.source
        self.assertIn('기본 시스템 설정', source)
        self.assertIn('AI 모델/API 관리', source)
        self.assertIn('페르소나 관리', source)
        self.assertIn("{% url 'persona_create' %}", source)
        self.assertIn("{% url 'persona_update' persona.id %}", source)
        self.assertIn("{% url 'persona_delete' persona.id %}", source)

    def test_writing_menu_no_longer_contains_persona_link(self):
        source = get_template('base.html').template.source
        writing_section = source[source.index('<!-- 0. 기초 쓰기 활동'):source.index('<!-- 9. 기타 학교생활')]
        self.assertNotIn('AI 페르소나 설정', writing_section)


@override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage'
)
class CsrfAndSessionConsistencyTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.client = Client()

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
        self.assertNotIn(
            "document.querySelector('[name=csrfmiddlewaretoken]')",
            script,
        )

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

        self.assertIn('get_token(request)', source)
        self.assertIn('request.session.cycle_key()', source)
        self.assertIn('rotate_token(request)', source)
        self.assertIn('select_for_update()', source)

    def test_login_get_forces_csrf_cookie_and_form_sync(self):
        response = self.client.get('/accounts/login/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)

        template = (
            Path(settings.BASE_DIR)
            / 'templates'
            / 'registration'
            / 'login.html'
        ).read_text(encoding='utf-8')
        self.assertIn('function syncLoginCsrfToken()', template)
        self.assertIn("getIngridCookie('csrftoken')", template)
        self.assertIn("loginForm.addEventListener('submit'", template)
        self.assertIn("window.addEventListener('pageshow'", template)

    def test_referrer_policy_keeps_same_origin_login_referer(self):
        self.assertEqual(settings.SECURE_REFERRER_POLICY, 'same-origin')

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
