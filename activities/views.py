from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from accounts.decorators import teacher_required
from .models import Activity, Question
from .forms import ActivityForm, QuestionForm

# 교사용: 평가 생성 페이지
@login_required
@teacher_required
def create_test(request):
    if request.method == 'POST':
        a_form = ActivityForm(request.POST)
        q_form = QuestionForm(request.POST)
        
        if a_form.is_valid() and q_form.is_valid():
            # 1. 활동(Activity) 저장
            activity = a_form.save(commit=False)
            activity.teacher = request.user
            # 선생님의 담당과목을 자동으로 입력 (없으면 '기타')
            activity.subject_name = request.user.subject.name if request.user.subject else "기타"
            activity.save()
            
            # 2. 문항(Question) 저장
            question = q_form.save(commit=False)
            question.activity = activity
            question.save()
            
            return redirect('dashboard') # 생성 후 대시보드로
    else:
        a_form = ActivityForm()
        q_form = QuestionForm()
        
    return render(request, 'activities/create_test.html', {'a_form': a_form, 'q_form': q_form})