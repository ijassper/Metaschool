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
        # 모든 필드에 부트스트랩 디자인(form-control) 자동 적용
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        
        # 각 필드별 placeholder(안내 문구) 설정
        self.fields['name'].widget.attrs['placeholder'] = '이름 (예: 홍길동)'
        self.fields['phone'].widget.attrs['placeholder'] = '010-1234-5678'
        self.fields['subject'].widget.attrs['placeholder'] = '담당 과목 (예: 영어, 수학)'

        # 비밀번호 필드에 ID 부여 (자바스크립트가 찾을 수 있게)
        # (주의: 장고 버전에 따라 필드명이 'password', 'password_confirmation'일 수도 있고 'pass1', 'pass2'일 수도 있음)
        # 화면에 'Password', 'Password confirmation'이라고 떴으므로 아래 이름을 사용합니다.
        
        if 'password' in self.fields:
            self.fields['password'].widget.attrs['placeholder'] = '비밀번호 (8자 이상)'
            self.fields['password'].widget.attrs['id'] = 'id_password' # JS용 ID
            
        if 'password_confirmation' in self.fields:
            self.fields['password_confirmation'].widget.attrs['placeholder'] = '비밀번호를 한 번 더 입력하세요'
            self.fields['password_confirmation'].widget.attrs['id'] = 'id_password_confirm' # JS용 ID

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