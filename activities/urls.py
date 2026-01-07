from django.urls import path
from .views import (
    create_test, activity_list, update_test, delete_test, 
    toggle_activity_status, activity_detail, activity_result # 추가
)

urlpatterns = [
    path('list/', activity_list, name='activity_list'),      # 목록
    path('create/', create_test, name='create_test'),        # 생성
    path('update/<int:activity_id>/', update_test, name='update_test'), # 수정
    path('delete/<int:activity_id>/', delete_test, name='delete_test'), # 삭제
    path('toggle/<int:activity_id>/', toggle_activity_status, name='toggle_activity_status'),   # 상태
    path('detail/<int:activity_id>/', activity_detail, name='activity_detail'), # 상세페이지
    path('result/<int:activity_id>/', activity_result, name='activity_result'), # 결과
]