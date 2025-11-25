from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class CustomUser(AbstractUser):
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
    
# 학생 데이터 모델
class Student(models.Model):
    # 담당 교사 (교사가 탈퇴하면 학생 정보도 같이 삭제됨)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    grade = models.IntegerField(verbose_name="학년")
    class_no = models.IntegerField(verbose_name="반")
    number = models.IntegerField(verbose_name="번호")
    name = models.CharField(max_length=20, verbose_name="이름")

    def __str__(self):
        return f"{self.grade}학년 {self.class_no}반 {self.name}"