from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, Student, Subject

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

        # [추가] 학교와 과목 필드를 '필수(Required)'로 강제 설정
        self.fields['school'].required = True
        self.fields['subject'].required = True
        
        # 각 필드별 placeholder(안내 문구) 설정
        self.fields['name'].widget.attrs['placeholder'] = '이름 (예: 홍길동)'
        self.fields['phone'].widget.attrs['placeholder'] = '010-1234-5678'
        
        # 담당 과목(subject) 필드 설정
        # 1. 쿼리셋 지정 (가나다순 정렬 필요하면 .order_by('name') 추가)
        self.fields['subject'].queryset = Subject.objects.all()
        # 2. 안내 문구 추가
        self.fields['subject'].empty_label = "-- 담당 교과 선택 --"
        # 3. 필수 입력 지정
        self.fields['subject'].required = True

        # # 비밀번호 필드 ID 지정 (자바스크립트 연결용)
        # # UserCreationForm의 기본 필드명은 'pass1'(비번), 'pass2'(확인) 입니다.
        # if 'pass1' in self.fields:
        #     self.fields['pass1'].widget.attrs['class'] = 'form-control'
        #     self.fields['pass1'].widget.attrs['placeholder'] = '비밀번호 (8자 이상)'
        #     self.fields['pass1'].widget.attrs['id'] = 'id_password'  # JS가 찾을 ID
            
        # if 'pass2' in self.fields:
        #     self.fields['pass2'].widget.attrs['class'] = 'form-control'
        #     self.fields['pass2'].widget.attrs['placeholder'] = '비밀번호를 한 번 더 입력하세요'
        #     self.fields['pass2'].widget.attrs['id'] = 'id_password_confirm' # JS가 찾을 ID

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
        fields = ['grade', 'class_no', 'number', 'name', 'email'] # 입력받을 항목
        labels = {
            'grade': '학년', 'class_no': '반', 'number': '번호', 
            'name': '이름', 'email': '학생 이메일 (ID)'
        }
        widgets = {
            'grade': forms.NumberInput(attrs={'class': 'form-control'}),
            'class_no': forms.NumberInput(attrs={'class': 'form-control'}),
            'number': forms.NumberInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }