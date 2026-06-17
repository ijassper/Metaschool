from django.contrib.auth import logout


class StudentSessionValidationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and getattr(user, 'is_student', False):
            current_session_key = request.session.session_key
            tracked_session_key = getattr(user, 'current_session_key', None)
            if tracked_session_key and current_session_key and tracked_session_key != current_session_key:
                logout(request)
        return self.get_response(request)