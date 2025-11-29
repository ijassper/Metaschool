from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Student, School, SystemConfig

# 1. 커스텀 유저 관리자 설정
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'name', 'school', 'subject', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('name', 'phone', 'school', 'subject')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('name', 'phone', 'school', 'subject')}),
    )

# 2. 시스템 설정 관리자 (편의성 강화)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ['key_name', 'value', 'description', 'updated_at']
    search_fields = ['key_name']

# 3. 모델 등록
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Student)
admin.site.register(School)
admin.site.register(SystemConfig, SystemConfigAdmin) # ★ 여기 등록됨!