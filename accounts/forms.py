from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, Student

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        # 폼에 표시될 필드 순서와 종류를 지정
        fields = ('email', 'name', 'phone', 'school', 'subject')

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