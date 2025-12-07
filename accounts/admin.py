from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Student, School, SystemConfig, PromptTemplate, PromptCategory, PromptLengthOption
from django.utils.html import format_html   # For custom HTML rendering

# 1. 사용자(교사) 관리 화면 설정
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'name', 'role', 'school', 'is_active'] # role 추가
    list_filter = ['role', 'school'] # 등급별 필터링
    list_editable = ['role'] # ★ 목록에서 바로 등급 수정 가능하게 설정!
    search_fields = ['email', 'name']
    
    fieldsets = UserAdmin.fieldsets + (
        ('추가 정보', {'fields': ('name', 'phone', 'school', 'subject', 'role')}), # 상세 페이지에 role 추가
    )

# 2. 시스템 설정(API 키) 관리 화면 설정
@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ['key_name', 'value', 'description', 'updated_at']
    search_fields = ['key_name']

# 3. 카테고리 트리 뷰 구현
@admin.register(PromptCategory)
class PromptCategoryAdmin(admin.ModelAdmin):
    list_display = ['get_tree_name_html', 'parent'] # 이름 대신 트리 형태 함수 사용
    ordering = ['parent__id', 'id'] # 부모끼리, 자식끼리 모아서 정렬

    # 트리 구조를 시각적으로 표현하는 함수
    def get_tree_name_html(self, obj):
        # 1단계: 대분류 (굵게 표시)
        if obj.parent is None:
            return format_html("<b>📂 {}</b>", obj.name)
        
        # 2단계: 중분류 (들여쓰기 4칸)
        elif obj.parent.parent is None:
            return format_html(
                "&nbsp;&nbsp;&nbsp;&nbsp;└─ 📁 {}", 
                obj.name
            )
            
        # 3단계: 소분류 (들여쓰기 8칸)
        else:
            return format_html(
                "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└─ 📄 {}", 
                obj.name
            )
    
    get_tree_name_html.short_description = '카테고리 구조'

# 4. 프롬프트 템플릿 관리자
@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ['category', 'title', 'length_option']
    list_filter = ['category']
    search_fields = ['title']

# 5. 분량 옵션 관리자
@admin.register(PromptLengthOption)
class PromptLengthOptionAdmin(admin.ModelAdmin):
    list_display = ['label', 'value']

# 6. 나머지 모델들 (학생, 학교)
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['grade', 'class_no', 'number', 'name', 'teacher']
    search_fields = ['name']

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'office', 'level', 'code']
    search_fields = ['name', 'code']