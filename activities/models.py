from django.db import models
from django.conf import settings
from accounts.models import Student

class Activity(models.Model):
    # 선생님 & 과목 정보 (자동 입력)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject_name = models.CharField(max_length=50, verbose_name="과목명") # 선생님 과목 자동 저장
    
    # 스케치의 입력 항목들
    section = models.CharField(max_length=100, verbose_name="평가영역명") # 예: 문학
    title = models.CharField(max_length=200, verbose_name="평가 주제")

    # 평가 대상 학생들 (Many-to-Many)
    # blank=True로 두어 나중에 추가할 수도 있게 함
    target_students = models.ManyToManyField(Student, blank=True, related_name='activities', verbose_name="평가 대상 학생")
    
    # 관리 정보
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False, verbose_name="평가 진행중") # 학생에게 보이기 여부

    def __str__(self):
        return f"[{self.subject_name}] {self.title}"

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