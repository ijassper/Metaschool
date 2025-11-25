from django.urls import path
from .views import SignUpView, mypage, student_upload, student_create

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path("mypage/", mypage, name="mypage"),
    path("student/upload/", student_upload, name="student_upload"),
    path("student/create/", student_create, name="student_create"),
]