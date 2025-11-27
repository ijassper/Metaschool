from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, Student

# 교사 회원가입 폼
class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        # 필드 순서 중요: 이메일을 가장 먼저 입력받음 (username 제외)
        fields = ('email', 'name', 'phone', 'school', 'subject')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # [핵심] 모든 필드에 부트스트랩 디자인(form-control) 자동 적용
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        
        # 각 필드별 placeholder(안내 문구) 설정
        self.fields['name'].widget.attrs['placeholder'] = '이름 (예: 홍길동)'
        self.fields['phone'].widget.attrs['placeholder'] = '010-1234-5678'
        self.fields['subject'].widget.attrs['placeholder'] = '담당 과목 (예: 영어, 수학)'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email  # 이메일을 아이디로 사용
        if commit:
            user.save()
        return user

# 학생 등록 폼
class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['grade', 'class_no', 'number', 'name'] # 입력받을 항목
        labels = {
            'grade': '학년',
            'class_no': '반',
            'number': '번호',
            'name': '이름',
        }
        widgets = {
            'grade': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '예: 1'}),
            'class_no': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '예: 3'}),
            'number': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '예: 15'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '이름 입력'}),
        }