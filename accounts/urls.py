from django.urls import path
from .views import SignUpView, mypage, student_upload, student_create, search_school

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path("mypage/", mypage, name="mypage"),
    path("student/upload/", student_upload, name="student_upload"),
    path("student/create/", student_create, name="student_create"),
    path("search/school/", search_school, name="search_school"), # 학교 검색 URL
]