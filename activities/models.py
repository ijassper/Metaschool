import os # 파일 경로 처리
from django.db import models
from django.conf import settings
from accounts.models import Student
from django.utils import timezone


class Activity(models.Model):
    # --- [1. 분류 및 유형] ---
    CATEGORY_CHOICES = [
        ('ESSAY', '교과 논술형 평가'),
        ('SUBJECT_ACTIVITY', '교과 수업활동 평가'),
        ('SCHOOL_EVENT', '교내 행사활동'),
        ('CREATIVE', '자율활동'),
        ('CLUB', '동아리활동'),
        ('CAREER', '진로활동'),
        ('SCHOOL_LIFE', '기타 학교생활'),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='ESSAY', verbose_name="활동 유형")
    sub_category = models.CharField(max_length=50, blank=True, null=True, verbose_name="소메뉴명")
    
    # --- [2. 소속 및 담당] ---
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="담당 교사")
    subject_name = models.CharField(max_length=50, verbose_name="과목명/활동분류") 
    section = models.CharField(max_length=100, verbose_name="평가영역/활동명") 
    title = models.CharField(max_length=200, verbose_name="주제")

    # --- [3. 활동 상세 내용] ---
    # 여러 textarea를 합쳐서 저장하거나 단일 문항을 저장하는 필드
    question = models.TextField(verbose_name="평가/활동 문항", blank=True)
    reference_material = models.TextField(null=True, blank=True, verbose_name="참고 자료")
    conditions = models.TextField(null=True, blank=True, verbose_name="작성 조건")
    attachment = models.FileField(upload_to='activity_files/%Y/%m/%d/', null=True, blank=True, verbose_name="첨부파일")
    
    # --- [4. 응시 및 제한 설정] ---
    EXAM_MODE_CHOICES = [
        ('CLOSED_LOCK', '폐쇄형 + 복사금지'),
        ('CLOSED_FREE', '폐쇄형 + 복사허용'),
        ('OPEN_LOCK', '개방형 + 복사금지'),
        ('OPEN_FREE', '개방형 + 복사허용'),
    ]
    exam_mode = models.CharField(max_length=11, choices=EXAM_MODE_CHOICES, default='CLOSED_LOCK', verbose_name="응시 환경")
    allow_edit_after_submission = models.BooleanField(default=True, verbose_name="제출 후 수정 허용")
    char_limit = models.IntegerField(default=0, verbose_name="분량 제한(자)") # 0은 무제한
    result = models.TextField(blank=True, verbose_name="평가 결과/피드백", help_text="학생에게 보여줄 피드백")

    # --- [5. 시간 관리 (핵심)] ---
    # 평가 생성일: 교사가 저장 버튼을 누른 시점 (자동 저장)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="평가 생성일")
    # 수업 일시: 실제 활동이 일어나는 시간 (직접 입력)
    activity_date = models.DateTimeField(null=True, blank=True, verbose_name="수업/활동 일시")
    # 제출 기한: 학생 응시 마감 시간 (직접 입력)
    deadline = models.DateTimeField(null=True, blank=True, verbose_name="제출 기한")
    # AI 분석 완료 시간 (시스템 기록)
    ai_updated_at = models.DateTimeField(null=True, blank=True, verbose_name="AI 분석 일시")

    # [기타 중요 정보 (AI 분석용)]
    achievement_standard = models.TextField(blank=True, null=True, verbose_name="성취 기준")
    evaluation_elements = models.TextField(blank=True, null=True, verbose_name="평가 요소")

    # [학생 답안지 문항 제목 커스텀]
    # 교사가 "활동 내용", "성과" 등을 직접 입력하여 저장
    q1_title = models.CharField(max_length=100, default="항목 1", verbose_name="문항 1 제목")
    q2_title = models.CharField(max_length=100, default="항목 2", verbose_name="문항 2 제목")
    q3_title = models.CharField(max_length=100, default="항목 3", verbose_name="문항 3 제목")

    # --- [6. 대상 및 상태] ---
    target_students = models.ManyToManyField('accounts.Student', blank=True, related_name='activities', verbose_name="대상 학생")
    is_active = models.BooleanField(default=False, verbose_name="활성화 여부")

    # --- [기타 중요 정보 (AI 분석용)] ---
    achievement_standard = models.TextField(blank=True, null=True, verbose_name="성취 기준")
    evaluation_elements = models.TextField(blank=True, null=True, verbose_name="평가 요소")

    # 특정 학생이 최종 제출을 완료했는지 확인하는 함수
    def get_student_answer(self, student):
        """특정 학생이 이 활동에 대해 작성한 답안 객체를 반환 (없으면 None)"""
        # Answer 모델을 함수 내부에서 임포트하여 순환 참조 에러를 방지합니다.
        from .models import Answer
        return Answer.objects.filter(question__activity=self, student=student).first()

    class Meta:
        verbose_name = "활동 및 평가"
        verbose_name_plural = "활동 및 평가 목록"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_category_display()}] {self.title}"

    # 제출된 답안 수와 대상 학생 수 계산을 위한 프로퍼티
    @property
    def submit_count(self):
        """실제 제출을 완료한 학생 수 계산"""
        from .models import Answer
        return Answer.objects.filter(question__activity=self, submitted_at__isnull=False).count()

    # 제출률 계산 프로퍼티
    @property
    def target_count(self):
        """전체 응시 대상 학생 수"""
        return self.target_students.count()
    
    # 상태를 실시간으로 판단하는 프로퍼티
    @property
    def is_effectively_active(self):
        return self.is_attainable

    @property
    def is_attainable(self):
        if not self.is_active:
            return False
        if self.deadline and timezone.now() > self.deadline:
            return False
        return True

    @property
    def is_viewable(self):
        return True

    def get_student_exam_state(self, answer=None):
        if answer and answer.submitted_at:
            if self.allow_edit_after_submission and self.is_attainable:
                return "submitted_editable"
            return "submitted_locked"
        if not self.is_attainable:
            return "unavailable"
        return "available"

    def can_student_enter(self, answer=None):
        if not self.is_attainable:
            return False
        if answer and answer.submitted_at and not self.allow_edit_after_submission:
            return False
        return True

    @property
    def status_text(self):
        if self.deadline and timezone.now() > self.deadline:
            return "마감됨"
        if self.is_attainable:
            return "진행중"
        return "대기중"

    @property
    def status_code(self):
        if self.deadline and timezone.now() > self.deadline:
            return "CLOSED"
        if self.is_attainable:
            return "ONGOING"
        return "READY"

    def get_status_display(self):
        return self.status_text

    # 파일명만 추출하는 프로퍼티
    @property
    def filename(self):
        if self.attachment:
            # 파일 경로에서 마지막 이름만 추출 (예: 'abc.pdf')
            return os.path.basename(self.attachment.name)
        return ""

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
    # 기존 content는 유지(호환성)하되, 항목별 답변 필드 추가
    ans_q1 = models.TextField(blank=True, null=True, verbose_name="항목 1 답변")
    ans_q2 = models.TextField(blank=True, null=True, verbose_name="항목 2 답변")
    ans_q3 = models.TextField(blank=True, null=True, verbose_name="항목 3 답변")
    content = models.TextField(verbose_name="통합 답안", blank=True) # 전체 합본용
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="제출/수정 시간")
    activity_log = models.TextField(blank=True, default="", verbose_name="활동 로그")
    ai_result = models.TextField(blank=True, null=True, verbose_name="AI 분석 결과")
    ai_updated_at = models.DateTimeField(null=True, blank=True, verbose_name="AI 분석 일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="마지막 수정 시간")
    
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

# AI 분석 결과 모델 (다중 결과 지원)
class AnalysisResult(models.Model):
    answer = models.ForeignKey('Answer', on_delete=models.CASCADE, related_name='analysis_results')
    result_content = models.TextField(verbose_name="AI 분석 결과")
    prompt_system = models.TextField(verbose_name="사용된 프롬프트")
    temperature = models.FloatField(default=0.7, verbose_name="창의성 온도")
    ai_model = models.CharField(max_length=50, default='gemini-2.0-flash', verbose_name="AI 모델")
    work_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="분석 작업명")
    batch_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="분석 세션 ID")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="분석 생성일")
    
    class Meta:
        verbose_name = "AI 분석 결과"
        verbose_name_plural = "AI 분석 결과 목록"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.answer.student.name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

# 다중 파일을 저장하기 위한 모델 (ActivityFile)
class ActivityFile(models.Model):
    # 어떤 활동에 속한 파일인지 연결 (ForeignKey)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='activity_files/%Y/%m/%d/', verbose_name="첨부파일")
    created_at = models.DateTimeField(auto_now_add=True)

    # 파일명만 추출하는 프로퍼티 (기존 Activity에 있던 로직을 여기로 이동)
    @property
    def filename(self):
        if self.file:
            return os.path.basename(self.file.name)
        return ""

    class Meta:
        verbose_name = "평가/활동 첨부파일"
        verbose_name_plural = "평가/활동 첨부파일 목록"
