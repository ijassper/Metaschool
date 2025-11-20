from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    # 이메일을 아이디로 사용하므로 username은 더 이상 필수 필드가 아님
    username = models.CharField(max_length=150, unique=False, null=True, blank=True)
    email = models.EmailField(unique=True, verbose_name='email address')

    # 우리가 추가하고자 하는 필드들
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    school = models.CharField(max_length=100)
    subject = models.CharField(max_length=100)

    # 이 필드를 로그인 ID로 사용
    USERNAME_FIELD = 'email'
    # 관리자 계정 생성 시 필수적으로 물어볼 필드 (email은 USERNAME_FIELD라 기본 포함)
    REQUIRED_FIELDS = ['name']

    def __str__(self):
        return self.email