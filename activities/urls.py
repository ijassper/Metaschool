from django.urls import path
from .views import create_test, activity_list, update_test, delete_test

urlpatterns = [
    path('list/', activity_list, name='activity_list'),      # 목록
    path('create/', create_test, name='create_test'),        # 생성
    path('update/<int:activity_id>/', update_test, name='update_test'), # 수정
    path('delete/<int:activity_id>/', delete_test, name='delete_test'), # 삭제
]