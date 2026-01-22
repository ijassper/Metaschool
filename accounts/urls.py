from django.contrib.auth.views import LoginView
from django.urls import path
from .forms import CustomAuthenticationForm # 교사, 학생 로그인
from .views import (
    SignUpView, student_list, mypage, student_upload, student_create, search_school, dashboard, approve_teacher,
    check_email_duplicate, ai_generator_step1, ai_generator_step2, # 추가
    api_process_one_row, api_download_excel, # 추가
    reset_student_password, student_delete, # 추가
)

urlpatterns = [
    path("login/", LoginView.as_view(
        template_name="registration/login.html",
        authentication_form=CustomAuthenticationForm # # 교사, 학생 로그인
    ), name="login"),
    path('signup/', SignUpView.as_view(), name='signup'),
    path("dashboard/", dashboard, name="dashboard"),    # 대시보드 URL
    path("mypage/", mypage, name="mypage"),
    path("student-list/", student_list, name="student_list"),
    path("student/upload/", student_upload, name="student_upload"), # 엑셀 업로드 URL
    path("student/create/", student_create, name="student_create"), # 학생 개별 등록 URL
    path("search/school/", search_school, name="search_school"), # 학교 검색 URL
    path('check-email/', check_email_duplicate, name='check_email'), # 이메일 중복 체크 URL
    path('approve-teacher/<int:user_id>/', approve_teacher, name='approve_teacher'),    # 교사 승인 URL
    path('ai/step1/', ai_generator_step1, name='ai_generator_step1'),   # AI 엑셀 업로드 URL
    path('ai/step2/', ai_generator_step2, name='ai_generator_step2'),   # AI 열 선택 및 실행 URL
    path('ai/step1/', ai_generator_step1, name='ai_generator_step1'),   # AI 엑셀 업로드 URL
    path('ai/step2/', ai_generator_step2, name='ai_generator_step2'),   # AI 열 선택 및 실행 URL
    path('api/process-row/', api_process_one_row, name='api_process_one_row'),  # 한 줄씩 AI 처리하는 API
    path('api/download-excel/', api_download_excel, name='api_download_excel'), # 최종 엑셀 다운로드
    path('student/reset-pw/<int:student_id>/', reset_student_password, name='reset_student_password'),  # 비밀번호 초기화 
    path('student/delete/<int:student_id>/', student_delete, name='student_delete'), # 학생 삭제
]