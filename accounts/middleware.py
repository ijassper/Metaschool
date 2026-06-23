import logging
from urllib.parse import urlencode

from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.cache import patch_cache_control


logger = logging.getLogger(__name__)


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
