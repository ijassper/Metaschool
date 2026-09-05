import os # 파일 경로 처리
from django.db import models
from django.conf import settings
from accounts.models import Student
from django.utils import timezone


class Activity(models.Model):
    COPY_PROTECTED_EXAM_MODES = frozenset({'CLOSED_LOCK', 'OPEN_LOCK'})

    # --- [1. 분류 및 유형] ---
    CATEGORY_CHOICES = [
        ('ESSAY', '교과 논술형 평가'),
        ('SUBJECT_ACTIVITY', '교과 수업활동'),
        ('SCHOOL_EVENT', '교내 행사활동'),
        ('CREATIVE', '자율활동'),
        ('CLUB', '동아리활동'),
        ('CAREER', '진로활동'),
        ('SCHOOL_LIFE', '기타 학교생활'),
        ('WRITING', '기초 쓰기 활동'),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='ESSAY', verbose_name="활동 유형")
    sub_category = models.CharField(max_length=50, blank=True, null=True, verbose_name="소메뉴명")
    
    # --- [2. 소속 및 담당] ---
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="담당 교사")
    subject_name = models.CharField(max_length=50, verbose_name="과목명/활동분류") 
    section = models.TextField(verbose_name="평가영역/활동명")
    title = models.TextField(verbose_name="주제")

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

    # --- [4-1. 타자 연습 전용 설정] ---
    TYPING_TYPE_CHOICES = [
        ('SHORT_MISSION', '단시간 미션'),
        ('SHORT_TEAM', '단시간 팀플레이'),
        ('LONG_SELF', '장기간 자율 훈련'),
    ]
    TYPING_POSITION_CHOICES = [
        ('LEFT', '왼손 키보드 연습'),
        ('RIGHT', '오른손 키보드 연습'),
        ('BOTH', '양손 키보드 연습'),
        ('WORD', '단어 연습'),
        ('SENTENCE', '문장 연습'),
        ('PARAGRAPH', '문단 연습'),
    ]
    TYPING_LEVEL_CHOICES = [
        ('BEGINNER_0', '타자 처음 왕초보'),
        ('BEGINNER_1', '독수리 타자'),
        ('INTERMEDIATE', '키보드 더듬더듬'),
        ('ADVANCED', '약간 능숙'),
        ('FAST', '고속 타자'),
        ('MASTER', '초고수 타자'),
    ]
    typing_type = models.CharField(max_length=20, choices=TYPING_TYPE_CHOICES, blank=True, default='', verbose_name="타자 연습 유형")
    typing_position = models.CharField(max_length=20, choices=TYPING_POSITION_CHOICES, blank=True, default='', verbose_name="타자 연습 위치")
    typing_level = models.CharField(max_length=20, choices=TYPING_LEVEL_CHOICES, blank=True, default='', verbose_name="타자 연습 수준")
    duration = models.PositiveIntegerField(null=True, blank=True, verbose_name="활동 시간(분)")
    show_keyboard = models.BooleanField(default=True, verbose_name="화면 키보드 표시")
    target_data = models.TextField(blank=True, default='', verbose_name="타자 연습 지문 데이터")

    # --- [4-2. 수업 노트/연습장 전용 설정] ---
    NOTE_TEMPLATE_CHOICES = [
        ('BLANK', '무지'), ('LINED_LARGE', '줄노트(대)'),
        ('LINED_MEDIUM', '줄노트(중)'), ('LINED_SMALL', '줄노트(소)'),
        ('MANUSCRIPT', '원고지'),
    ]
    NOTE_PALETTE_CHOICES = [
        ('WHITE', '무지(흰 배경)'), ('CREAM', '크림'), ('PINK', '핑크'), ('LAVENDER', '라벤더'),
        ('BLUE', '블루'), ('MINT', '민트'),
    ]
    NOTE_PALETTE_HEX = {
        'WHITE': '#FFFFFF', 'CREAM': '#FFF9F0', 'PINK': '#FFF1F7', 'LAVENDER': '#F7F1FF',
        'BLUE': '#EFF7FF', 'MINT': '#EFFBF6',
    }
    note_template = models.CharField(max_length=20, choices=NOTE_TEMPLATE_CHOICES, blank=True, default='', verbose_name='노트 양식')
    note_background = models.CharField(max_length=20, choices=NOTE_PALETTE_CHOICES, blank=True, default='', verbose_name='노트 배경 색상')

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
    q1_title = models.TextField(default="항목 1", verbose_name="문항 1 제목")
    q2_title = models.TextField(default="항목 2", verbose_name="문항 2 제목")
    q3_title = models.TextField(default="항목 3", verbose_name="문항 3 제목")

    # --- [6. 대상 및 상태] ---
    target_students = models.ManyToManyField('accounts.Student', blank=True, related_name='activities', verbose_name="대상 학생")
    is_active = models.BooleanField(default=False, verbose_name="활성화 여부")

    # --- [기타 중요 정보 (AI 분석용)] ---
    achievement_standard = models.TextField(blank=True, null=True, verbose_name="성취 기준")
    evaluation_elements = models.TextField(blank=True, null=True, verbose_name="평가 요소")

    # 특정 학생이 답안 제출을 완료했는지 확인하는 함수
    def get_student_answer(self, student):
        """특정 학생이 이 활동에 대해 작성한 답안 객체를 반환 (없으면 None)"""
        # Answer 모델을 함수 내부에서 임포트하여 순환 참조 에러를 방지합니다.
        from .models import Answer
        return Answer.objects.filter(question__activity=self, student=student).first()

    @property
    def is_notebook(self):
        return self.sub_category == '수업 노트/연습장'

    @property
    def note_background_hex(self):
        return self.NOTE_PALETTE_HEX.get(self.note_background, self.NOTE_PALETTE_HEX['CREAM'])

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
    def is_copy_protected(self):
        """복사 제한이 적용되는 응시 환경인지 반환합니다."""
        return self.exam_mode in self.COPY_PROTECTED_EXAM_MODES or self.exam_mode == 'CLOSED'

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
    class Score(models.IntegerChoices):
        ZERO = 0, "0점"
        ONE = 1, "1점"
        TWO = 2, "2점"
        THREE = 3, "3점"
        FOUR = 4, "4점"
        FIVE = 5, "5점"

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    # 기존 content는 유지(호환성)하되, 항목별 답변 필드 추가
    ans_q1 = models.TextField(blank=True, null=True, verbose_name="항목 1 답변")
    ans_q2 = models.TextField(blank=True, null=True, verbose_name="항목 2 답변")
    ans_q3 = models.TextField(blank=True, null=True, verbose_name="항목 3 답변")
    notebook_pages = models.JSONField(default=list, blank=True, verbose_name="노트 페이지")
    score = models.PositiveSmallIntegerField(
        choices=Score.choices,
        null=True,
        blank=True,
        verbose_name="퀵 점수",
    )
    content = models.TextField(verbose_name="통합 답안", blank=True) # 전체 합본용
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="제출/수정 시간")
    activity_log = models.TextField(blank=True, default="", verbose_name="활동 로그")
    ai_result = models.TextField(blank=True, null=True, verbose_name="AI 분석 결과")
    ai_updated_at = models.DateTimeField(null=True, blank=True, verbose_name="AI 분석 일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="마지막 수정 시간")

    @property
    def display_content(self):
        """실제로 작성된 답안만 조합하여 비활성 문항의 빈 [] 표기를 제거합니다."""
        activity = self.question.activity
        answer_items = [
            (activity.q1_title, self.ans_q1),
            (activity.q2_title, self.ans_q2),
            (activity.q3_title, self.ans_q3),
        ]
        written_items = [
            ((title or '').strip(), (answer or '').strip())
            for title, answer in answer_items
            if (answer or '').strip()
        ]

        if len(written_items) == 1:
            return written_items[0][1]
        if written_items:
            return '\n\n'.join(
                f'[{title}]\n{answer}' if title else answer
                for title, answer in written_items
            )

        # 레거시 통합 답안은 독립된 빈 대괄호 행만 제거합니다.
        return '\n'.join(
            line for line in (self.content or '').splitlines()
            if line.strip() != '[]'
        ).strip()

    @property
    def has_started(self):
        """점수 레코드 존재와 무관한 실제 응시 시작 여부입니다."""
        return bool(
            self.submitted_at
            or (self.activity_log or '').strip()
            or self.display_content.strip()
        )

    def participation_status(self, *, deadline_passed=False):
        """응시 이력을 기준으로 미응시·미제출·제출 상태를 구분합니다."""
        if self.absence_type:
            return '결시'
        has_content = bool(self.display_content.strip())
        if self.submitted_at:
            return '제출 완료' if has_content else '백지 제출'
        if not self.has_started:
            return '미응시'
        return '미제출' if deadline_passed else '응시 중'
    
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


class AnswerDraftRevision(models.Model):
    """학생이 복구할 수 있도록 제한적으로 보관하는 자동저장 답안 이력입니다."""

    class SaveReason(models.TextChoices):
        PERIODIC = 'PERIODIC', '정기 자동저장'
        DESTRUCTIVE_EDIT = 'DESTRUCTIVE_EDIT', '대량 삭제 직전'
        MANUAL = 'MANUAL', '수동 임시저장'
        PAGE_EXIT = 'PAGE_EXIT', '페이지 이동 전'

    answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        related_name='draft_revisions',
        verbose_name='답안',
    )
    content_snapshot = models.JSONField(default=dict, verbose_name='답안 스냅샷')
    char_count = models.PositiveIntegerField(default=0, verbose_name='공백 제외 글자 수')
    fingerprint = models.CharField(max_length=64, verbose_name='내용 지문')
    save_reason = models.CharField(
        max_length=20,
        choices=SaveReason.choices,
        default=SaveReason.PERIODIC,
        verbose_name='저장 사유',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='저장 일시')

    class Meta:
        verbose_name = '자동저장 답안 이력'
        verbose_name_plural = '자동저장 답안 이력 목록'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['answer', '-created_at'], name='draft_revision_answer_idx'),
        ]

    def __str__(self):
        return f'{self.answer} · {self.created_at:%Y-%m-%d %H:%M:%S}'


class ActivityStudentScore(models.Model):
    """답안 및 응시 상태와 독립적으로 보관하는 활동별 학생 점수입니다."""

    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name='student_scores',
        verbose_name='활동',
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='activity_scores',
        verbose_name='학생',
    )
    score = models.PositiveSmallIntegerField(choices=Answer.Score.choices, verbose_name='점수')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성 일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정 일시')

    class Meta:
        verbose_name = '활동별 학생 점수'
        verbose_name_plural = '활동별 학생 점수 목록'
        constraints = [
            models.UniqueConstraint(
                fields=['activity', 'student'],
                name='unique_activity_student_score',
            )
        ]
        indexes = [
            models.Index(fields=['activity', 'student'], name='activity_student_score_idx')
        ]

    def __str__(self):
        return f'{self.activity} · {self.student} · {self.score}점'

# AI 분석 결과 모델 (다중 결과 지원)
class AnalysisResult(models.Model):
    answer = models.ForeignKey('Answer', on_delete=models.CASCADE, related_name='analysis_results')
    result_content = models.TextField(verbose_name="AI 분석 결과")
    prompt_system = models.TextField(verbose_name="사용된 프롬프트")
    temperature = models.FloatField(default=0.7, verbose_name="창의성 온도")
    ai_model = models.CharField(max_length=50, default='gemini-2.0-flash', verbose_name="AI 모델")
    work_name = models.TextField(null=True, blank=True, verbose_name="분석 작업명")
    batch_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="분석 세션 ID")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="분석 생성일")
    
    class Meta:
        verbose_name = "AI 분석 결과"
        verbose_name_plural = "AI 분석 결과 목록"
        ordering = ['-created_at']
    
    def __str__(self):
        created_at = timezone.localtime(self.created_at)
        return f"{self.answer.student.name} - {created_at.strftime('%Y-%m-%d %H:%M')}"


class FeedbackResult(models.Model):
    """학생 답안을 기반으로 생성하고 교사가 최종 확정한 작업 기록입니다."""

    class TaskType(models.TextChoices):
        GRADING = 'grading', '채점/분석'
        FEEDBACK = 'feedback', '피드백'
        REWRITE = 'rewrite', '고쳐쓰기'
        RELAY = 'relay', '릴레이쓰기'

    student = models.ForeignKey(
        'accounts.Student', on_delete=models.CASCADE, related_name='feedback_results', verbose_name='학생'
    )
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name='feedback_results', verbose_name='활동'
    )
    answer = models.ForeignKey(
        'Answer', on_delete=models.CASCADE, related_name='feedback_results', verbose_name='원본 답안'
    )
    source_session = models.OneToOneField(
        'FeedbackSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='final_result',
        verbose_name='원본 피드백 작업 세션',
    )
    task_type = models.CharField(
        max_length=20, choices=TaskType.choices, default=TaskType.FEEDBACK, verbose_name='작업 유형'
    )
    feedback_title = models.TextField(max_length=150, blank=True, verbose_name='작업 제목')
    feedback_content = models.TextField(verbose_name='AI 피드백 본문')
    persona_used = models.JSONField(default=dict, blank=True, verbose_name='사용된 페르소나/어조 정보')
    is_published = models.BooleanField(default=False, verbose_name='학생 공개 여부')
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='학생 공개 일시')
    is_read = models.BooleanField(default=False, verbose_name='학생 열람 여부')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='학생 최초 열람 일시')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='저장 일시')

    class Meta:
        verbose_name = '학생 답안 작업 기록'
        verbose_name_plural = '학생 답안 작업 기록 목록'
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['answer', 'created_at'], name='feedback_answer_idx')]

    @property
    def type_name(self):
        return self.get_task_type_display()

    @property
    def display_title(self):
        return self.feedback_title.strip() if self.feedback_title else self.type_name

    @property
    def persona_name(self):
        if isinstance(self.persona_used, dict):
            return self.persona_used.get('persona_name', '')
        return str(self.persona_used or '')

    def __str__(self):
        return f'{self.student.name} - {self.display_title}'


class FeedbackSession(models.Model):
    """AI 초안과 교사의 수정 내용을 답안별 버전으로 보관하는 임시 작업 세션입니다."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', '임시 저장'
        FINAL = 'FINAL', '최종 저장'

    student = models.ForeignKey(
        'accounts.Student', on_delete=models.CASCADE, related_name='feedback_sessions', verbose_name='학생'
    )
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name='feedback_sessions', verbose_name='활동'
    )
    answer = models.ForeignKey(
        'Answer', on_delete=models.CASCADE, related_name='feedback_sessions', verbose_name='원본 답안'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feedback_sessions', verbose_name='작성 교사'
    )
    feedback_title = models.TextField(max_length=150, blank=True, verbose_name='피드백 제목')
    content = models.TextField(blank=True, verbose_name='피드백 본문')
    options_snapshot = models.JSONField(default=dict, blank=True, verbose_name='생성 옵션 스냅샷')
    version = models.PositiveIntegerField(verbose_name='버전')
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, verbose_name='저장 상태'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성 일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정 일시')

    class Meta:
        verbose_name = 'AI 피드백 작업 세션'
        verbose_name_plural = 'AI 피드백 작업 세션 목록'
        ordering = ['-version', '-id']
        constraints = [
            models.UniqueConstraint(fields=['answer', 'version'], name='unique_feedback_session_version')
        ]
        indexes = [models.Index(fields=['answer', '-version'], name='feedback_session_ver_idx')]

    @classmethod
    def make_unique_title(cls, *, answer, created_by, title, exclude_session_id=None):
        """같은 답안의 작업 제목이 겹치면 '(n)' 접미사를 붙여 새 제목을 반환합니다."""
        base_title = str(title or '').strip()[:150]
        if not base_title:
            return ''

        sessions = cls.objects.filter(answer=answer, created_by=created_by)
        if exclude_session_id:
            sessions = sessions.exclude(pk=exclude_session_id)
        if not sessions.filter(feedback_title__iexact=base_title).exists():
            return base_title

        sequence = 1
        while True:
            suffix = f' ({sequence})'
            candidate = f'{base_title[:150 - len(suffix)].rstrip()}{suffix}'
            if not sessions.filter(feedback_title__iexact=candidate).exists():
                return candidate
            sequence += 1

    def __str__(self):
        return f'{self.student.name} - v{self.version} {self.feedback_title}'

# 다중 파일을 저장하기 위한 모델 (ActivityFile)
class ActivityFile(models.Model):
    class ExtractionStatus(models.TextChoices):
        PENDING = 'PENDING', '추출 대기'
        READY = 'READY', '추출 완료'
        UNSUPPORTED = 'UNSUPPORTED', '미지원 형식'
        ERROR = 'ERROR', '추출 실패'

    # 어떤 활동에 속한 파일인지 연결 (ForeignKey)
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='activity_files/%Y/%m/%d/', verbose_name="첨부파일")
    created_at = models.DateTimeField(auto_now_add=True)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True, verbose_name='파일 해시')
    extraction_status = models.CharField(
        max_length=16,
        choices=ExtractionStatus.choices,
        default=ExtractionStatus.PENDING,
        verbose_name='텍스트 추출 상태',
    )
    extracted_text = models.TextField(blank=True, verbose_name='추출 텍스트')
    extracted_char_count = models.PositiveIntegerField(default=0, verbose_name='추출 글자 수')
    extracted_at = models.DateTimeField(null=True, blank=True, verbose_name='추출 일시')
    extraction_error = models.CharField(max_length=500, blank=True, verbose_name='추출 오류')

    # 파일명만 추출하는 프로퍼티 (기존 Activity에 있던 로직을 여기로 이동)
    @property
    def filename(self):
        if self.file:
            return os.path.basename(self.file.name)
        return ""

    class Meta:
        verbose_name = "평가/활동 첨부파일"
        verbose_name_plural = "평가/활동 첨부파일 목록"


class ActivityAnalysisContext(models.Model):
    """활동 공통 자료를 학생별 분석에서 재사용하기 위한 캐시입니다."""

    activity = models.OneToOneField(
        Activity,
        on_delete=models.CASCADE,
        related_name='analysis_context_cache',
        verbose_name='활동',
    )
    source_fingerprint = models.CharField(max_length=64, db_index=True, verbose_name='원본 지문')
    structured_context = models.TextField(blank=True, verbose_name='구조화된 활동 컨텍스트')
    summary_text = models.TextField(blank=True, verbose_name='AI 분석용 요약본')
    summary_model = models.CharField(max_length=50, blank=True, verbose_name='요약 모델')
    summary_usage = models.JSONField(default=dict, blank=True, verbose_name='요약 토큰 사용량')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성 일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='갱신 일시')

    class Meta:
        verbose_name = '활동 AI 컨텍스트 캐시'
        verbose_name_plural = '활동 AI 컨텍스트 캐시 목록'

    def __str__(self):
        return f'{self.activity.title} 분석 컨텍스트'


class AIUsageLog(models.Model):
    class Operation(models.TextChoices):
        ATTACHMENT_OCR = 'ATTACHMENT_OCR', '첨부자료 OCR'
        CONTEXT_SUMMARY = 'CONTEXT_SUMMARY', '활동 자료 요약'
        STUDENT_ANALYSIS = 'STUDENT_ANALYSIS', '학생 답안 분석'

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_usage_logs',
        verbose_name='교사',
    )
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name='ai_usage_logs', verbose_name='활동'
    )
    answer = models.ForeignKey(
        'Answer', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_usage_logs', verbose_name='답안'
    )
    operation = models.CharField(max_length=24, choices=Operation.choices, verbose_name='작업')
    ai_model = models.CharField(max_length=50, verbose_name='AI 모델')
    prompt_tokens = models.PositiveIntegerField(default=0, verbose_name='입력 토큰')
    cached_tokens = models.PositiveIntegerField(default=0, verbose_name='캐시 입력 토큰')
    completion_tokens = models.PositiveIntegerField(default=0, verbose_name='출력 토큰')
    total_tokens = models.PositiveIntegerField(default=0, verbose_name='전체 토큰')
    estimated_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0, verbose_name='예상 비용(USD)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='사용 일시')

    class Meta:
        verbose_name = 'AI 토큰 사용 기록'
        verbose_name_plural = 'AI 토큰 사용 기록 목록'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['teacher', 'created_at'], name='ai_usage_teacher_idx')]

    def __str__(self):
        return f'{self.teacher} · {self.operation} · {self.total_tokens}'
