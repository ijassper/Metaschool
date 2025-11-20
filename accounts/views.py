from django.urls import reverse_lazy
from django.views import generic
from .forms import CustomUserCreationForm

class SignUpView(generic.CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login') # 가입 성공 시 로그인 페이지로 이동
    template_name = 'registration/signup.html' # 사용할 HTML 파일