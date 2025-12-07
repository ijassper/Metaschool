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

# 2. 사용자(교사) 모델 (이메일 필드 명시!)
class CustomUser(AbstractUser):
    # 회원 등급 정의 (학생 < 게스트 < 일반 < 대표 < 관리자)
    class Role(models.TextChoices):
        STUDENT = 'STUDENT', '학생'             # 학생
        GUEST = 'GUEST', '게스트 교사'           # 가입 직후 (승인 대기)
        TEACHER = 'TEACHER', '일반 교사'         # 승인된 교사
        LEADER = 'LEADER', '학교 대표 교사'       # 중간 관리자
        ADMIN = 'ADMIN', '최고 관리자'           # 시스템 운영자 (superuser와 별개로 표시용)

    # 이메일 필드를 명시적으로 선언하고 유일한 값(unique)으로 설정
    email = models.EmailField(verbose_name='아이디(이메일)', max_length=255, unique=True)
    
    name = models.CharField(max_length=100, verbose_name="이름")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="연락처")
    
    # [수정] blank=True, null=True를 제거하거나 blank=False로 변경
    # 단, on_delete=models.SET_NULL 때문에 null=True는 DB 안전을 위해 남겨두는 게 좋습니다.
    # 하지만 blank=False로 설정하면 폼(Form)에서는 입력을 강제합니다.

    school = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=False, related_name='teachers', verbose_name="소속 학교")
    subject = models.CharField(max_length=100, blank=False, null=True, verbose_name="담당 과목")

    # [중요] 
    # USERNAME_FIELD를 'email'로 바꾸지 않고 'username'으로 유지합니다.
    # 이유: 학생은 이메일 없이 '학번코드(숫자)'로 로그인해야 하기 때문입니다.
    # - 교사: username 칸에 '이메일' 저장
    # - 학생: username 칸에 '학번코드' 저장
    
    # 등급 필드 (기본값: 게스트 교사)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.GUEST, verbose_name="회원 등급")

    REQUIRED_FIELDS = ['email', 'name']

    def __str__(self):
        return f"[{self.get_role_display()}] {self.name}"

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

# 1. 프롬프트 카테고리 (계층형 구조)
class PromptCategory(models.Model):
    name = models.CharField(max_length=50, verbose_name="카테고리명")
    # 부모가 없으면 대분류, 있으면 하위분류 (Self 참조)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name="상위 카테고리")

    def __str__(self):
        # 최상위 카테고리면 이름만 표시 (예: 동아리활동)
        if self.parent is None:
            return self.name
        # 하위 카테고리면 경로 표시 (예: 동아리활동 > 건축분야)
        return f"{self.parent.name} > {self.name}"

    class Meta:
        verbose_name = "프롬프트 카테고리"
        verbose_name_plural = "1. 프롬프트 카테고리 관리"

# 2. 분량 옵션 (예: 500자, 1000자)
class PromptLengthOption(models.Model):
    label = models.CharField(max_length=50, verbose_name="화면 표시 이름 (예: 1000 Byte)")
    value = models.CharField(max_length=200, verbose_name="실제 프롬프트 내용 (예: 1000 Byte 내외로 작성)")

    def __str__(self):
        return self.label

    class Meta:
        verbose_name_plural = "2. 분량 옵션 (Byte)"

# 3. 프롬프트 템플릿
class PromptTemplate(models.Model):
    # 카테고리 연결
    category = models.ForeignKey(PromptCategory, on_delete=models.SET_NULL, null=True, verbose_name="카테고리(소분류)")
    title = models.CharField(max_length=100, verbose_name="템플릿 제목")
    
    # 사용 가이드/설명
    description = models.TextField(verbose_name="사용 가이드(설명)", blank=True, help_text="선생님들에게 보여줄 팁이나 설명을 적으세요.")

    # 내용 필드
    context = models.TextField(verbose_name="프롬프트 맥락", blank=True)
    role = models.TextField(verbose_name="AI의 역할", blank=True)
    task = models.TextField(verbose_name="AI가 할 일", blank=True)
    output_example = models.TextField(verbose_name="원하는 결과값 예시", blank=True)
    
    # 분량 (직접 입력 대신 옵션 선택)
    length_option = models.ForeignKey(PromptLengthOption, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="분량 선택")

    def __str__(self):
        return f"[{self.category}] {self.title}"
    
    class Meta:
        verbose_name_plural = "3. 프롬프트 템플릿"