from pathlib import Path
import inspect
import json
import re
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse
from django.template.loader import get_template

from .middleware import AndroidStudentMinimumVersionMiddleware, StudentSessionValidationMiddleware
from .views import (
    _notify_admin_storage_risk,
    _should_trigger_proctor_cleanup,
    admin_system_settings,
    login_view,
    persona_create,
    student_app_download,
    student_app_install,
    student_app_qr,
    student_app_version,
)


class ProctorCleanupLoginTriggerTests(SimpleTestCase):
    def test_only_system_admin_triggers_cleanup(self):
        self.assertTrue(_should_trigger_proctor_cleanup(SimpleNamespace(role='ADMIN', is_superuser=False)))
        self.assertTrue(_should_trigger_proctor_cleanup(SimpleNamespace(role='TEACHER', is_superuser=True)))
        self.assertFalse(_should_trigger_proctor_cleanup(SimpleNamespace(role='LEADER', is_superuser=False)))
        self.assertFalse(_should_trigger_proctor_cleanup(SimpleNamespace(role='TEACHER', is_superuser=False)))

    def test_login_view_contains_non_blocking_cleanup_trigger(self):
        source = inspect.getsource(login_view)
        self.assertIn('schedule_cleanup_after_admin_login()', source)
        self.assertIn('_notify_admin_storage_risk(request)', source)

    def test_storage_warning_is_silent_below_eighty_percent(self):
        request = SimpleNamespace()
        with patch('accounts.views.get_proctor_storage_report', return_value={
            'level': 'normal', 'used_percent': 61.2,
        }), patch('accounts.views.messages.warning') as warning, patch(
            'accounts.views.messages.error'
        ) as error:
            _notify_admin_storage_risk(request)
        warning.assert_not_called()
        error.assert_not_called()

    def test_storage_warning_is_shown_at_warning_level(self):
        request = SimpleNamespace()
        with patch('accounts.views.get_proctor_storage_report', return_value={
            'level': 'warning', 'used_percent': 84.5,
        }), patch('accounts.views.messages.warning') as warning:
            _notify_admin_storage_risk(request)
        self.assertIn('84.5%', warning.call_args.args[1])
        self.assertIn('90%', warning.call_args.args[1])

    def test_storage_failure_is_shown_as_error(self):
        request = SimpleNamespace()
        with patch('accounts.views.get_proctor_storage_report', return_value={
            'level': 'blocked', 'used_percent': None,
        }), patch('accounts.views.messages.error') as error:
            _notify_admin_storage_risk(request)
        self.assertIn('확인할 수 없습니다', error.call_args.args[1])


@override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage'
)
class StudentAppDistributionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_teacher_can_open_install_center(self):
        request = self.factory.get(reverse('student_app_install'))
        request.user = SimpleNamespace(is_authenticated=True, role='TEACHER')

        with patch('accounts.views._android_student_apk_path', return_value=None):
            response = student_app_install(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn('설치 파일을 준비하고 있습니다'.encode(), response.content)

    def test_student_cannot_open_install_center(self):
        request = self.factory.get(reverse('student_app_install'))
        request.user = SimpleNamespace(is_authenticated=True, role='STUDENT')
        request._messages = SimpleNamespace(add=lambda *args, **kwargs: None)

        with patch('accounts.views.messages.error'):
            response = student_app_install(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    @override_settings(ANDROID_STUDENT_APP_VERSION='0.3.5')
    def test_download_serves_apk_with_versioned_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            apk_path = Path(temp_dir) / 'student.apk'
            apk_path.write_bytes(b'ingrid-apk')
            with patch('accounts.views._android_student_apk_path', return_value=apk_path):
                response = student_app_download(self.factory.get(reverse('student_app_download')))

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/vnd.android.package-archive')
            self.assertIn('ingrid-student-0.3.5.apk', response['Content-Disposition'])
            response.close()

    def test_qr_endpoint_returns_svg_for_download_url(self):
        with tempfile.NamedTemporaryFile(suffix='.apk') as apk:
            with patch('accounts.views._android_student_apk_path', return_value=Path(apk.name)):
                response = student_app_qr(self.factory.get(reverse('student_app_qr')))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertIn(b'<svg', response.content)

    @override_settings(
        ANDROID_STUDENT_APP_VERSION='0.2.0',
        ANDROID_STUDENT_APP_VERSION_CODE=11,
        ANDROID_STUDENT_MIN_VERSION='0.1.8',
        ANDROID_STUDENT_MIN_VERSION_CODE=9,
    )
    def test_version_endpoint_exposes_current_release(self):
        with patch('accounts.views._android_student_apk_path', return_value=Path('release.apk')):
            response = student_app_version(self.factory.get(reverse('student_app_version')))

        payload = json.loads(response.content)
        self.assertEqual(payload['version_code'], 11)
        self.assertEqual(payload['version_name'], '0.2.0')
        self.assertEqual(payload['minimum_version_code'], 9)
        self.assertEqual(payload['minimum_version_name'], '0.1.8')
        self.assertTrue(payload['apk_available'])
        self.assertTrue(payload['download_url'].endswith(reverse('student_app_download')))


class AndroidStudentMinimumVersionMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.next_response = HttpResponse('allowed')
        self.middleware = AndroidStudentMinimumVersionMiddleware(lambda request: self.next_response)

    @override_settings(ANDROID_STUDENT_MIN_VERSION='0.3.6')
    def test_legacy_android_app_is_redirected_to_required_update(self):
        request = self.factory.get('/accounts/login/', HTTP_USER_AGENT='Chrome IngridStudentAndroid/0.1')
        response = self.middleware(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('student_app_update_required'))

    @override_settings(ANDROID_STUDENT_MIN_VERSION='0.3.6')
    def test_supported_android_app_can_continue(self):
        request = self.factory.get('/accounts/login/', HTTP_USER_AGENT='Chrome IngridStudentAndroid/0.3.6')
        response = self.middleware(request)
        self.assertIs(response, self.next_response)

    @override_settings(ANDROID_STUDENT_MIN_VERSION='0.3.6')
    def test_browser_is_not_affected(self):
        request = self.factory.get('/accounts/login/', HTTP_USER_AGENT='Chrome/140.0')
        response = self.middleware(request)
        self.assertIs(response, self.next_response)

    @override_settings(ANDROID_STUDENT_MIN_VERSION='0.3.6')
    def test_update_endpoints_remain_available_to_legacy_app(self):
        for path in (
            reverse('student_app_version'),
            reverse('student_app_download'),
            reverse('student_app_update_required'),
        ):
            request = self.factory.get(path, HTTP_USER_AGENT='Chrome IngridStudentAndroid/0.1')
            self.assertIs(self.middleware(request), self.next_response)


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
        self.assertIn('감독 기록 자동 정리', source)
        self.assertIn('name="settings_section" value="proctor_cleanup"', source)
        self.assertIn('서버 웹 저장공간', source)
        self.assertIn('저장 중단', source)
        self.assertNotIn('시연(Demo) 모드', source)
        self.assertNotIn('name="demo_mode"', source)
        self.assertIn('오늘의 감독 운영 현황', source)
        self.assertIn('proctor_operations.live', source)
        self.assertIn('proctor_status=attention', source)
        self.assertIn('감독 화면', source)

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
