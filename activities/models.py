from django.db import models
from django.conf import settings
from accounts.models import Student
from django.utils import timezone

class Activity(models.Model):
    # 1. 활동 유형 분류 (7가지 메뉴 대응)
    CATEGORY_CHOICES = [
        ('ESSAY', '교과 논술형 평가'),
        ('SUBJECT', '교과 수업활동'),
        ('EVENT', '교내 행사활동'),
        ('CREATIVE', '자율활동'),
        ('CAREER', '진로활동'),
        ('CLASS', '학급활동'),
        ('CUSTOM', '교사 맞춤형 분석'),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='ESSAY', verbose_name="활동 유형")
    result = models.TextField(blank=True, verbose_name="평가 결과", help_text="학생에게 보여줄 피드백") # 결과 텍스트

    # 응시 환경 설정 (OPEN: 개방형, CLOSED: 폐쇄형)
    EXAM_MODE_CHOICES = [
        ('OPEN', '개방형 (참고자료 확인 가능, 멀티태스킹 허용)'),
        ('CLOSED', '폐쇄형 (브라우저 이탈 방지, 키보드 보안 적용)'),
    ]
    exam_mode = models.CharField(
        max_length=10, 
        choices=EXAM_MODE_CHOICES, 
        default='CLOSED', 
        verbose_name="응시 환경 유형"
    )

    attachment = models.FileField(
        upload_to='activity_files/%Y/%m/%d/', 
        null=True, 
        blank=True, 
        verbose_name="첨부파일"
    )

    # 2. 기본 정보
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_name = models.CharField(max_length=50, verbose_name="과목명/활동분류") 
    section = models.CharField(max_length=100, verbose_name="평가영역/활동명") 
    title = models.CharField(max_length=200, verbose_name="주제")

    # 3. 상세 내용 (신규 추가)
    question = models.TextField(verbose_name="평가/활동 문항", blank=True)
    reference_material = models.TextField(null=True, blank=True, verbose_name="참고 자료")
    conditions = models.TextField(null=True, blank=True, verbose_name="작성 조건")
    
    # 4. 제한 및 기한 (신규 추가)
    deadline = models.DateTimeField(null=True, blank=True, verbose_name="제출 기한")
    char_limit = models.IntegerField(default=0, verbose_name="분량 제한(자)") # 0은 무제한

    # 5. 대상 및 상태
    target_students = models.ManyToManyField('accounts.Student', blank=True, related_name='activities', verbose_name="대상 학생")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False, verbose_name="활성화 여부")

    class Meta:
        verbose_name = "활동 및 평가"
        verbose_name_plural = "활동 및 평가 목록"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_category_display()}] {self.title}"

    # 상태를 동적으로 판단하는 프로퍼티
    @property
    def status_text(self):
        now = timezone.now()
        if not self.is_active:
            return "대기중"
        if self.deadline and now > self.deadline:
            return "마감됨"
        return "진행중"

class Question(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='questions')
    
    # 스케치의 상세 항목들
    content = models.TextField(verbose_name="평가 문항")
    reference = models.TextField(blank=True, verbose_name="참고 자료")
    conditions = models.TextField(blank=True, verbose_name="작성 조건")
    max_length = models.IntegerField(null=True, blank=True, verbose_name="분량 제한(자)")

    def __str__(self):
        return f"문항: {self.activity.title}"

# 학생 답안
class Answer(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    content = models.TextField(verbose_name="학생 답안")
    submitted_at = models.DateTimeField(auto_now=True, verbose_name="제출/수정 시간")
    activity_log = models.TextField(blank=True, default="", verbose_name="활동 로그")
    ai_result = models.TextField(blank=True, null=True, verbose_name="AI 분석 결과")
    ai_updated_at = models.DateTimeField(null=True, blank=True, verbose_name="AI 분석 일시")
    
     # 결시 사유 선택지
    class Absence(models.TextChoices):
        NONE = '', '-'
        SICK = '병결', '병결'
        PUBLIC = '공결', '공결'
        ACK = '인정결', '인정결'
        NACK = '미인정결', '미인정결'

    # 결시 사유 필드
    absence_type = models.CharField(
        max_length=10, 
        choices=Absence.choices, 
        default=Absence.NONE, 
        verbose_name="결시 사유"
    )
    # 선생님 특이사항 메모 (비공개)
    note = models.TextField(blank=True, verbose_name="특이사항(교사 메모)")