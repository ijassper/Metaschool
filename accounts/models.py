from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings 

# 1. 학교 정보 모델
class School(models.Model):
    class Level(models.TextChoices):
        HIGH = 'HIGH', '고등학교'
        MIDDLE = 'MID', '중학교'
        ELEMENTARY = 'ELEM', '초등학교'
        ETC = 'ETC', '기타'

    office = models.CharField(max_length=50, verbose_name="교육청")
    name = models.CharField(max_length=50, verbose_name="학교명")
    code = models.CharField(max_length=20, unique=True, verbose_name="나이스코드")
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.HIGH, verbose_name="학교급")

    def __str__(self):
        return f"[{self.get_level_display()}] {self.name}"

# 2. 사용자(교사) 모델 수정 (이메일 필드 명시!)
class CustomUser(AbstractUser):
    # 이메일 필드를 명시적으로 선언하고 유일한 값(unique)으로 설정
    email = models.EmailField(verbose_name='아이디(이메일)', max_length=255, unique=True)
    
    name = models.CharField(max_length=100, verbose_name="이름")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="연락처")
    school = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=True, related_name='teachers', verbose_name="소속 학교")
    subject = models.CharField(max_length=100, blank=True, null=True, verbose_name="담당 과목")

    # [중요] 
    # USERNAME_FIELD를 'email'로 바꾸지 않고 'username'으로 유지합니다.
    # 이유: 학생은 이메일 없이 '학번코드(숫자)'로 로그인해야 하기 때문입니다.
    # - 교사: username 칸에 '이메일' 저장
    # - 학생: username 칸에 '학번코드' 저장
    
    REQUIRED_FIELDS = ['email', 'name'] # 슈퍼유저 만들 때 물어볼 항목

    def __str__(self):
        return self.name if self.name else self.username

# 3. 학생 모델
class Student(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    grade = models.IntegerField(verbose_name="학년")
    class_no = models.IntegerField(verbose_name="반")
    number = models.IntegerField(verbose_name="번호")
    name = models.CharField(max_length=20, verbose_name="이름")

    def __str__(self):
        return f"{self.grade}학년 {self.class_no}반 {self.name}"
    
# 시스템 전역 설정 저장소 (API Key 등)
class SystemConfig(models.Model):
    key_name = models.CharField(max_length=50, unique=True, verbose_name="설정 키 (영어)")
    value = models.TextField(verbose_name="설정 값") # API 키가 길 수 있으니 TextField 사용
    description = models.CharField(max_length=200, blank=True, verbose_name="설명")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일시")

    def __str__(self):
        return f"{self.key_name} ({self.description})"

    class Meta:
        verbose_name = "시스템 설정"
        verbose_name_plural = "시스템 설정 목록"

# [신규] 프롬프트 템플릿 (관리자가 미리 만들어두는 예시)
class PromptTemplate(models.Model):
    title = models.CharField(max_length=100, verbose_name="템플릿 제목 (예: 동아리 활동)")
    
    # 세부 항목들
    context = models.TextField(verbose_name="프롬프트 맥락", blank=True)
    role = models.TextField(verbose_name="AI의 역할", blank=True)
    task = models.TextField(verbose_name="AI가 할 일", blank=True)
    output_example = models.TextField(verbose_name="원하는 결과값 예시", blank=True)
    length = models.CharField(max_length=100, verbose_name="원하는 분량", blank=True)

    def __str__(self):
        return self.title