from django.contrib import admin
from .models import (
    AIUsageLog,
    Activity,
    ActivityAnalysisContext,
    ActivityFile,
    Answer,
    FeedbackResult,
    Question,
)

# 1. 문항(Question)을 평가(Activity) 수정 화면에서 바로 볼 수 있게 설정
class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0  # 기본으로 보여줄 빈 칸 개수

# 2. 평가(Activity) 관리자 설정
@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject_name', 'section', 'teacher', 'is_active', 'created_at']
    list_filter = ['is_active', 'subject_name']
    search_fields = ['title', 'subject_name']
    inlines = [QuestionInline] # 평가 상세 페이지에서 문항도 같이 수정 가능

# 3. 답안(Answer) 관리자 설정 (★ 가장 중요한 부분)
@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    # 목록에서 보여줄 항목: 학생, 질문(평가제목), 제출일, AI분석여부
    list_display = ['student', 'get_activity_title', 'submitted_at', 'has_ai_result']
    list_filter = ['question__activity', 'submitted_at']
    search_fields = ['student__name', 'content']

    # 평가 제목을 가져오는 함수
    def get_activity_title(self, obj):
        return obj.question.activity.title
    get_activity_title.short_description = '평가 주제'

    # AI 분석 결과가 있는지 체크표시(V)로 보여주는 함수
    def has_ai_result(self, obj):
        return bool(obj.ai_result)
    has_ai_result.boolean = True # 아이콘으로 표시
    has_ai_result.short_description = 'AI 분석 완료'

# 문항 모델도 단독으로 관리하고 싶을 경우 등록
admin.site.register(Question)


@admin.register(FeedbackResult)
class FeedbackResultAdmin(admin.ModelAdmin):
    list_display = ['student', 'activity', 'task_type', 'created_at']
    list_filter = ['task_type', 'activity', 'created_at']
    search_fields = ['student__name', 'activity__title', 'feedback_content']
    readonly_fields = ['created_at']


@admin.register(ActivityFile)
class ActivityFileAdmin(admin.ModelAdmin):
    list_display = ['filename', 'activity', 'extraction_status', 'extracted_char_count', 'extracted_at']
    list_filter = ['extraction_status', 'created_at']
    search_fields = ['activity__title', 'file', 'content_hash']
    readonly_fields = ['content_hash', 'extracted_text', 'extracted_char_count', 'extracted_at', 'extraction_error']


@admin.register(ActivityAnalysisContext)
class ActivityAnalysisContextAdmin(admin.ModelAdmin):
    list_display = ['activity', 'summary_model', 'updated_at']
    search_fields = ['activity__title', 'source_fingerprint']
    readonly_fields = ['source_fingerprint', 'structured_context', 'summary_text', 'summary_usage', 'created_at', 'updated_at']


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'activity', 'operation', 'ai_model', 'total_tokens', 'estimated_cost_usd', 'created_at']
    list_filter = ['operation', 'ai_model', 'created_at']
    search_fields = ['teacher__name', 'activity__title']
    readonly_fields = [
        'teacher', 'activity', 'answer', 'operation', 'ai_model', 'prompt_tokens',
        'cached_tokens', 'completion_tokens', 'total_tokens', 'estimated_cost_usd', 'created_at',
    ]
