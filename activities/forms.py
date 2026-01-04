from django import forms
from .models import Activity, Question

class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ['section', 'title'] # 과목은 자동
        widgets = {
            'section': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '예: 문학, 읽기'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '주제를 입력하세요'}),
        }

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['content', 'reference', 'conditions', 'max_length']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': '질문 내용을 입력하세요'}),
            'reference': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '제시문 또는 참고 자료'}),
            'conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': '예: 3문단으로 구성, 두괄식 작성'}),
            'max_length': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
        }