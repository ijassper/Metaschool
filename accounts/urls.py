from django.urls import path
from .views import SignUpView, mypage 

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path("mypage/", mypage, name="mypage"),
]