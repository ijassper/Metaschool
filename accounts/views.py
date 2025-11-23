from django.urls import reverse_lazy
from django.views import generic
from .forms import CustomUserCreationForm

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Student

class SignUpView(generic.CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login') # 가입 성공 시 로그인 페이지로 이동
    template_name = 'registration/signup.html' # 사용할 HTML 파일

# 마이페이지 (학생 명렬표 보기)
@login_required  # 로그인을 해야만 볼 수 있음
def mypage(request):
    # 로그인한 선생님(request.user)이 담당하는 학생들만 가져오기
    my_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')
    
    return render(request, 'accounts/mypage.html', {'students': my_students})