from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Student, School, SystemConfig, PromptTemplate, PromptCategory, PromptLengthOption 

# 1. 사용자(교사) 관리 화면 설정
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'name', 'school', 'subject', 'is_staff']
    # 관리자 페이지에서 수정할 수 있는 필드 설정
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('name', 'phone', 'school', 'subject')}),
    )

# 2. 시스템 설정(API 키) 관리 화면 설정
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ['key_name', 'value', 'description', 'updated_at']
    search_fields = ['key_name']

# 프롬프트 템플릿 관리자
@admin.register(PromptCategory)
class PromptCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent']
    list_filter = ['parent']

@admin.register(PromptLengthOption)
class PromptLengthOptionAdmin(admin.ModelAdmin):
    list_display = ['label', 'value']

@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ['category', 'title', 'length_option']
    list_filter = ['category']
    search_fields = ['title']

# 3. 관리자 페이지에 등록
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Student)
admin.site.register(School)
admin.site.register(SystemConfig, SystemConfigAdmin)    # 여기 등록