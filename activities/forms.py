from django import forms
from .models import Activity, Question
from .models import Answer  # 답안

class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ['subject_name', 'section', 'title']
        widgets = {
            'subject_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '과목명을 입력하세요 (예: 국어)'}),
            'section': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '예: 문학, 읽기'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '주제를 입력하세요'}),
        }

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['content', 'reference', 'conditions', 'max_length']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10, 'placeholder': '질문 내용을 입력하세요'}),
            'reference': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': '제시문 또는 참고 자료'}),
            'conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': '예: 3문단으로 구성, 두괄식 작성'}),
            'max_length': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0', 'type': 'number'}),
        }

# 학생 답안 작성 폼
class AnswerForm(forms.ModelForm):
    class Meta:
        model = Answer
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 20,  # 답안지는 길어야 하니까 높게 설정
                'placeholder': '여기에 답안을 작성하세요.',
                'style': 'resize: none;' # 크기 조절 막기 (깔끔하게)
            }),
        }