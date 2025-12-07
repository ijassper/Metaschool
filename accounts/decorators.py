
from django.shortcuts import redirect
from django.contrib import messages

def teacher_required(function):
    def wrap(request, *args, **kwargs):
        # 1. 로그인이 안 되어 있으면 -> 로그인 페이지로
        if not request.user.is_authenticated:
            return redirect('login')
        
        # 2. 게스트(GUEST)이거나 학생(STUDENT)이면 -> 대시보드로 쫓아냄
        if request.user.role == 'GUEST':
            messages.warning(request, "관리자 승인 후 이용 가능합니다.")
            return redirect('dashboard')
        
        if request.user.role == 'STUDENT':
            messages.warning(request, "학생은 접근할 수 없는 페이지입니다.")
            return redirect('dashboard')
            
        # 3. 통과 (일반 교사 이상)
        return function(request, *args, **kwargs)
    return wrap