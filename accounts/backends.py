from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        try:
            # 1. 입력받은 값이 이메일 전체인지, 아니면 @ 앞부분(아이디)인지 확인
            # 예: 'student'라고 쳤으면 -> 'student@...' 로 시작하는 이메일을 찾음
            user = User.objects.get(
                Q(username=username) | 
                Q(email=username) | 
                Q(email__startswith=f"{username}@")  # ★ 아이디만 쳐도 검색됨
            )
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # 혹시 중복된 앞자리가 있으면 첫 번째 사람 선택 (드문 경우)
            user = User.objects.filter(email__startswith=f"{username}@").first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None