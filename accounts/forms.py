from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, Student

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        # 필드 순서 중요: 이메일을 가장 먼저 입력받음 (username 제외)
        fields = ('email', 'name', 'phone', 'school', 'subject')

    # [핵심] 저장할 때: 입력받은 '이메일'을 '아이디(username)' 칸에도 똑같이 복사해서 저장
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email  # ★ 이메일을 아이디로 사용
        if commit:
            user.save()
        return user
    
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