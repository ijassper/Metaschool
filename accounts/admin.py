from django.contrib import admin, messages # 메시지 표시용 userAdmin
from django.contrib.auth.admin import UserAdmin
from django.utils.safestring import mark_safe # HTML 출력을 위해 필요
from django.db.models import Case, When # For conditional ordering
from django.utils.html import format_html   # For custom HTML rendering
from django.forms import Textarea   
from .models import CustomUser, Student, School, SystemConfig, PromptTemplate, PromptCategory, PromptLengthOption, Subject

# 일괄 변경 액션 함수
@admin.action(description='✅ 선택된 교사를 [메타고등학교]로 변경')
def set_school_to_meta(modeladmin, request, queryset):
    try:
        # DB에 등록된 '메타고등학교' 찾기 (이름 정확해야 함!)
        meta_school = School.objects.get(name='메타고등학교')
        updated_count = queryset.update(school=meta_school)
        modeladmin.message_user(request, f"{updated_count}명의 선생님을 메타고등학교로 이동시켰습니다.")
    except School.DoesNotExist:
        modeladmin.message_user(request, "❌ '메타고등학교'가 학교 목록에 없습니다. 먼저 학교를 등록해주세요.", level=messages.ERROR)
        
# 1. 사용자(교사) 관리 화면 설정
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'name', 'role', 'school', 'is_active'] # role 추가
    list_filter = ['role', 'school'] # 등급별 필터링
    list_editable = ['role'] # ★ 목록에서 바로 등급 수정 가능하게 설정!
    search_fields = ['email', 'name']
    actions = [set_school_to_meta] # 일괄 변경 액션 등록

    # ★ 학생 등급(STUDENT)은 목록에서 제외하는 로직
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # role이 'STUDENT'가 아닌 사람만 보여줘라
        return qs.exclude(role='STUDENT') 
    
    fieldsets = UserAdmin.fieldsets + (
        ('추가 정보', {'fields': ('name', 'phone', 'school', 'subject', 'role')}), # 상세 페이지에 role 추가
    )

# 2. 시스템 설정(API 키) 관리 화면 설정
@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ['key_name', 'value', 'description', 'updated_at']
    search_fields = ['key_name']

# 3. 카테고리 트리 뷰 구현 (족보순 정렬 + 계단식 디자인)
@admin.register(PromptCategory)
class PromptCategoryAdmin(admin.ModelAdmin):
    list_display = ['get_tree_name_html', 'parent'] # 이름 대신 트리 형태 함수 사용
    list_display_links = ['get_tree_name_html']
    ordering = ['parent__id', 'id'] # 부모끼리, 자식끼리 모아서 정렬

    # ★ 1. 데이터를 가져올 때 '족보 순서'대로 줄 세우는 마법의 함수
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        # 전체 데이터를 가져와서 파이썬 메모리에서 트리를 만듭니다.
        all_cats = list(qs)
        children_map = {c.id: [] for c in all_cats}
        roots = []

        for c in all_cats:
            if c.parent_id:
                if c.parent_id in children_map:
                    children_map[c.parent_id].append(c)
            else:
                roots.append(c)

        # 재귀함수로 정렬된 ID 리스트 생성 (DFS 방식)
        sorted_ids = []
        def add_nodes(nodes):
            # 같은 레벨에서는 이름순 정렬
            nodes.sort(key=lambda x: x.name)
            for node in nodes:
                sorted_ids.append(node.id)
                # 자식이 있으면 바로 그 밑으로 붙임
                if node.id in children_map:
                    add_nodes(children_map[node.id])
        
        add_nodes(roots)

        # 정렬된 ID 순서대로 DB에 다시 요청 (Case/When 문법 사용)
        preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(sorted_ids)])
        return qs.filter(pk__in=sorted_ids).order_by(preserved)

    # ★ 2. 계단식 디자인 (기존 코드 유지)
    def get_tree_name_html(self, obj):
        if obj.parent is None:
            return format_html(
                "<span style='font-weight:bold; font-size: 1.1em; color: #2c3e50;'>📂 {}</span>", 
                obj.name
            )
        elif obj.parent.parent is None:
            return format_html(
                "<span style='margin-left: 30px; color: #555;'>└─ 📁 {}</span>", 
                obj.name
            )
        else:
            return format_html(
                "<span style='margin-left: 60px; color: #777;'>└─ 📄 {}</span>", 
                obj.name
            )
    
    get_tree_name_html.short_description = '카테고리 구조 (트리)'

# 4. 프롬프트 템플릿 관리자
@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ['category', 'title', 'length_option']
    list_filter = ['category']
    search_fields = ['title']

    # ★ [추가] 입력창 크기 조절 함수
    def formfield_for_dbfield(self, db_field, **kwargs):
        
        # 1. 'AI가 수행할 작업' (task) 필드 크게 만들기
        if db_field.name == 'task':
            # rows: 줄 수 (높이), style: 가로 폭
            kwargs['widget'] = Textarea(attrs={'rows': 20, 'style': 'width: 90%;'})
            
        # 2. (선택사항) '활동의 맥락...' (context) 필드도 키우고 싶다면?
        if db_field.name == 'context':
            kwargs['widget'] = Textarea(attrs={'rows': 15, 'style': 'width: 90%;'})

        # 3. (선택사항) '결과 예시' (output_example) 필드
        if db_field.name == 'output_example':
            kwargs['widget'] = Textarea(attrs={'rows': 10, 'style': 'width: 90%;'})

        return super().formfield_for_dbfield(db_field, **kwargs)

# 5. 분량 옵션 관리자
@admin.register(PromptLengthOption)
class PromptLengthOptionAdmin(admin.ModelAdmin):
    list_display = ['label', 'value']

# 6. 나머지 모델들 (학생, 학교)
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    # 목록에 보여줄 항목들
    list_display = ['grade', 'class_no', 'number', 'name', 'get_school', 'teacher']
    
    # ★ [핵심] 우측 필터 추가
    # teacher__school : 선생님의 소속 학교로 필터링
    list_filter = ['teacher__school', 'grade', 'class_no']
    
    # 검색 기능
    search_fields = ['name', 'teacher__name']

    # 학교 이름 가져오기
    def get_school(self, obj):
        return obj.teacher.school.name if obj.teacher.school else "-"
    get_school.short_description = '학교'

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'office', 'level', 'code']
    search_fields = ['name', 'code']

# 교과목 관리자
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['name']

