from django.urls import path

from .views import (
    SignUpView,
    admin_system_settings,
    admin_teacher_list,
    admin_teacher_update,
    ai_generator_step1,
    ai_generator_step2,
    api_download_excel,
    api_process_one_row,
    approve_teacher,
    check_email_duplicate,
    dashboard,
    deny_teacher,
    login_view,
    profile_settings,
    profile_update,
    reset_student_password,
    search_school,
    student_bulk_action,
    student_create,
    student_create_hub,
    student_delete,
    student_export_excel,
    student_list,
    student_upload,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path("dashboard/", dashboard, name="dashboard"),
    path("profile-settings/", profile_settings, name="profile_settings"),
    path("profile/update/", profile_update, name="profile_update"),

    path("student-list/", student_list, name="student_list"),
    path("student/upload/", student_upload, name="student_upload"),
    path("student/create/", student_create, name="student_create"),
    path("student/create-hub/", student_create_hub, name="student_create_hub"),
    path("student/export-excel/", student_export_excel, name="student_export_excel"),
    path("student/bulk-action/", student_bulk_action, name="student_bulk_action"),
    path("student/reset-pw/<int:student_id>/", reset_student_password, name="reset_student_password"),
    path("student/delete/<int:student_id>/", student_delete, name="student_delete"),

    path("search/school/", search_school, name="search_school"),
    path("check-email/", check_email_duplicate, name="check_email"),

    path("approve-teacher/<int:user_id>/", approve_teacher, name="approve_teacher"),
    path("deny-teacher/<int:user_id>/", deny_teacher, name="deny_teacher"),

    path("ai/step1/", ai_generator_step1, name="ai_generator_step1"),
    path("ai/step2/", ai_generator_step2, name="ai_generator_step2"),
    path("api/process-row/", api_process_one_row, name="api_process_one_row"),
    path("api/download-excel/", api_download_excel, name="api_download_excel"),

    path("system-settings/", admin_system_settings, name="admin_system_settings"),
    path("admin/teachers/", admin_teacher_list, name="admin_teacher_list"),
    path("admin/teachers/<int:user_id>/update/", admin_teacher_update, name="admin_teacher_update"),
]
