from django.urls import path
from .views import (
    create_test, activity_list, update_test, delete_test, 
    toggle_activity_status, activity_detail, activity_result, take_test,
    answer_detail, answer_delete, save_note, update_absence, log_activity, activity_analysis 
)

urlpatterns = [
    path('list/', activity_list, name='activity_list'),      # 목록
    path('create/', create_test, name='create_test'),        # 생성
    path('update/<int:activity_id>/', update_test, name='update_test'), # 수정
    path('delete/<int:activity_id>/', delete_test, name='delete_test'), # 삭제
    path('toggle/<int:activity_id>/', toggle_activity_status, name='toggle_activity_status'),   # 상태
    path('detail/<int:activity_id>/', activity_detail, name='activity_detail'), # 상세페이지
    path('result/<int:activity_id>/', activity_result, name='activity_result'), # 결과
    path('take/<int:activity_id>/', take_test, name='take_test'), # 응시
    path('answer/detail/<int:answer_id>/', answer_detail, name='answer_detail'),    # 답안 상세페이지
    path('answer/delete/<int:answer_id>/', answer_delete, name='answer_delete'),    # 답안 삭제
    path('api/update-absence/', update_absence, name='update_absence'), # 결시사유
    path('answer/note/<int:answer_id>/', save_note, name='save_note'),  # 특이사항 메모
    path('api/log/', log_activity, name='log_activity'), # 학생 답안 화면 이탈로그
    path('analysis/<int:activity_id>/', activity_analysis, name='activity_analysis'), # 결과 분석 페이지
]