
from django.shortcuts import redirect
from django.contrib import messages

def teacher_required(function):
    def wrap(request, *args, **kwargs):
        # 1. 로그인이 안 되어 있으면 -> 로그인 페이지로
        if not request.user.is_authenticated:
            return redirect('login')
        
        # 2. 학생 또는 승인 전 교사는 교사 전용 기능에 접근할 수 없음
        if request.user.role == 'STUDENT':
            messages.warning(request, "학생은 접근할 수 없는 페이지입니다.")
            return redirect('dashboard')

        if not getattr(request.user, 'is_approved', False):
            messages.warning(request, "승인 대기 중입니다. 대표 교사의 승인 후 이용 가능합니다.")
            return redirect('dashboard')
            
        # 3. 통과 (승인된 교사 이상)
        return function(request, *args, **kwargs)
    return wrap
