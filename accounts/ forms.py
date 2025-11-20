from django.contrib.auth.forms import UserCreationForm
from .models import User

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        # 폼에 표시될 필드 순서와 종류를 지정
        fields = ('email', 'name', 'phone', 'school', 'subject')