from django.urls import path
# 쪼개진 파일들로부터 함수를 각각 가져옵니다.
from .views.main_views import *
from .views.manage_views import *
from .views.exam_views import *
from .views.result_views import *
from .views.ai_views import *
from .views.export_views import *

urlpatterns = [
    # 1. 공통 및 목록 (main_views)
    path('find-account/', find_account, name='find_account'), 
    path('list/', unified_list, name='unified_list'),
    path('creative/', creative_list, name='creative_list'),
    path('detail/<int:activity_id>/', activity_detail, name='activity_detail'),
    path('creative/<int:pk>/', creative_detail, name='creative_detail'),

    # 2. 생성/수정/삭제 (manage_views)
    path('create/', unified_create, name='unified_create'),
    path('update/<int:activity_id>/', unified_update, name='unified_update'),
    path('delete/<int:activity_id>/', unified_delete, name='unified_delete'),
    path('toggle/<int:activity_id>/', toggle_activity_status, name='toggle_activity_status'),
    path('creative/create/', creative_create, name='creative_create'),
    path('creative/<int:pk>/edit/', creative_update, name='creative_update'),
    path('creative/<int:pk>/delete/', creative_delete, name='creative_delete'),

    # 3. 학생 응시 및 보안 (exam_views)
    path('take/<int:activity_id>/', take_test, name='take_test'),
    path('api/log/', log_activity, name='log_activity'),
    path('api/update-absence/', update_absence, name='update_absence'),

    # 4. 결과 및 답안 관리 (result_views)
    path('result/<int:activity_id>/', activity_result, name='activity_result'),
    path('answer/detail/<int:answer_id>/', answer_detail, name='answer_detail'),
    path('answer/delete/<int:answer_id>/', answer_delete, name='answer_delete'),
    path('answer/note/<int:answer_id>/', save_note, name='save_note'),

    # 5. AI 분석 (ai_views)
    path('analysis/<int:activity_id>/', activity_analysis, name='activity_analysis'),
    path('analysis/all/', integrated_analysis, name='integrated_analysis'),
    path('analysis-work/<int:activity_id>/', activity_analysis_work, name='activity_analysis_work'),
    path('api/process-db-row/', api_process_db_row, name='api_process_db_row'),

    # 6. 내보내기 (export_views)
    path('submission/export/<int:activity_id>/', submission_export_excel, name='submission_export_excel'),
    path('submission/export-docx/<int:activity_id>/', export_answer_sheets_docx, name='export_answer_sheets_docx'),
    path('analysis/export/<int:activity_id>/', analysis_export_excel, name='analysis_export_excel'),
]