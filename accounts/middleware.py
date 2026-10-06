import logging
import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.cache import patch_cache_control


logger = logging.getLogger(__name__)


class AndroidStudentMinimumVersionMiddleware:
    """지원 종료된 Ingrid Android 앱을 업데이트 화면으로 보냅니다."""

    USER_AGENT_PATTERN = re.compile(r'IngridStudentAndroid/([0-9]+(?:\.[0-9]+)*)', re.IGNORECASE)
    EXEMPT_PATHS = {
        '/accounts/student-app/version/',
        '/accounts/student-app/download/',
        '/accounts/student-app/update-required/',
    }
    EXEMPT_PREFIXES = ('/static/', '/media/', '/admin/')

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _version_tuple(value):
        return tuple(int(part) for part in str(value).split('.'))

    def __call__(self, request):
        match = self.USER_AGENT_PATTERN.search(request.META.get('HTTP_USER_AGENT', ''))
        if not match:
            return self.get_response(request)

        current_version = match.group(1)
        request.ingrid_android_version = current_version
        if request.path in self.EXEMPT_PATHS or request.path.startswith(self.EXEMPT_PREFIXES):
            return self.get_response(request)

        minimum_version = settings.ANDROID_STUDENT_MIN_VERSION
        if self._version_tuple(current_version) < self._version_tuple(minimum_version):
            return redirect('student_app_update_required')
        return self.get_response(request)


class StudentSessionValidationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and getattr(user, 'is_student', False):
            current_session_key = request.session.session_key
            tracked_session_key = getattr(user, 'current_session_key', None)

            if (
                tracked_session_key
                and current_session_key
                and tracked_session_key != current_session_key
            ):
                logger.info(
                    'Student session replaced: user_id=%s path=%s',
                    user.pk,
                    request.path,
                )
                logout(request)

                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    response = JsonResponse(
                        {
                            'status': 'error',
                            'code': 'SESSION_REPLACED',
                            'message': '다른 기기에서 로그인되어 현재 세션이 종료되었습니다.',
                        },
                        status=401,
                    )
                    response['X-Session-Expired'] = '1'
                    return self._disable_cache(response)

                login_url = f"/accounts/login/?{urlencode({'next': request.get_full_path()})}"
                return self._disable_cache(redirect(login_url))

        response = self.get_response(request)
        if (
            (user and user.is_authenticated)
            or request.path == '/accounts/login/'
        ):
            self._disable_cache(response)
        return response

    @staticmethod
    def _disable_cache(response):
        patch_cache_control(
            response,
            no_cache=True,
            no_store=True,
            must_revalidate=True,
            private=True,
        )
        response['Pragma'] = 'no-cache'
        return response
