from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        try:
            # 보안 강화: 전체 이메일 주소만 허용, 도메인 자동 완성 제거
            # 사용자가 입력한 문자열 그대로 정확히 일치하는 계정만 검색
            user = User.objects.get(
                Q(username=username) | 
                Q(email=username)
            )
        except User.DoesNotExist:
            return None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None