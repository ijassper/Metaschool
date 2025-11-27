import pandas as pd  # 엑셀 처리를 위해 필요
from django.urls import reverse_lazy
from django.http import JsonResponse  # 검색 기능을 위해 필요
from django.views import generic
from django.shortcuts import render, redirect
from django.contrib.auth import login  # 자동 로그인을 위해 필요
from django.contrib.auth.decorators import login_required
from django.contrib import messages  # 알림 메시지(성공/실패)를 위해 필요
from django.contrib.auth.hashers import make_password  # 비밀번호 암호화
from .forms import CustomUserCreationForm, StudentForm
from .models import Student, CustomUser, School  # Student, CustomUser, School 모델 모두 가져오기

# 1. 회원가입 뷰 (수정됨: 가입 후 자동 로그인 & 마이페이지 이동)
class SignUpView(generic.CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('mypage')  # 가입 성공 시 이동할 곳
    template_name = 'registration/signup.html'

    def form_valid(self, form):
        # 회원가입 정보 저장
        response = super().form_valid(form)
        # 저장된 유저 정보로 즉시 로그인 처리
        user = self.object
        login(self.request, user)
        return response

# 2. 마이페이지 뷰
@login_required
def mypage(request):
    # 로그인한 선생님(request.user)이 담당하는 학생들만 가져오기
    my_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')
    
    return render(request, 'accounts/mypage.html', {'students': my_students})

# 3. 엑셀 일괄 등록 뷰
@login_required
def student_upload(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        
        try:
            # 엑셀 파일 읽기
            df = pd.read_excel(excel_file)
            
            # 학교 코드 (임시: 1004) - 나중에 교사 정보에서 가져오도록 수정 가능
            school_code = "1004" 

            count = 0
            for index, row in df.iterrows():
                # 엑셀 데이터 추출 (엑셀 헤더가 '학년', '반', '번호', '이름'이어야 함)
                grade = int(row['학년'])
                class_no = int(row['반'])
                number = int(row['번호'])
                name = str(row['이름'])
                
                # A. 학생용 아이디 생성 (학교코드 + 학년 + 반2자리 + 번호2자리) -> 예: 100410105
                student_id = f"{school_code}{grade}{class_no:02d}{number:02d}"
                
                # B. 학생 계정(User) 생성 (이미 있으면 가져오고, 없으면 생성)
                user, created = CustomUser.objects.get_or_create(
                    username=student_id,
                    defaults={
                        'name': name,
                        'password': make_password("1234"), # 초기 비밀번호
                        'school': request.user.school,     # 교사의 학교 정보 상속
                        'is_active': True
                    }
                )

                # C. 학생 명부(Student) 테이블에 저장 (교사와 연결)
                # 만약 이미 등록된 학생이면(학년/반/번호/교사가 같으면) 중복 생성 방지
                Student.objects.get_or_create(
                    teacher=request.user,
                    grade=grade,
                    class_no=class_no,
                    number=number,
                    defaults={'name': name}
                )
                count += 1

            messages.success(request, f"{count}명의 학생이 성공적으로 등록되었습니다.")
            
        except Exception as e:
            messages.error(request, f"업로드 중 오류가 발생했습니다: {str(e)}")
            
    return redirect('mypage')

# 학교 검색 API (AJAX 요청 처리)
@login_required
def search_school(request):
    query = request.GET.get('q', '') # 검색어 가져오기
    if query:
        # 이름에 검색어가 포함된 학교 찾기 (최대 30개만)
        schools = School.objects.filter(name__contains=query)[:30]
        results = [{'id': s.id, 'name': s.name, 'office': s.office} for s in schools]
    else:
        results = []
    return JsonResponse({'results': results})


# 학생 개별 등록 페이지
@login_required
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        # HTML 화면에서 보낸 학교의 DB ID (예: 15)
        school_db_id = request.POST.get('school_select_id') 

        if form.is_valid() and school_db_id:
            student = form.save(commit=False)
            student.teacher = request.user # 담당 교사는 로그인한 선생님
            
            # --- 학생 아이디 생성 로직 ---
            # 1. 학교 DB ID를 4자리 문자로 변환 (예: 15 -> '0015')
            school_code_str = f"{int(school_db_id):04d}"
            
            # 2. 아이디 조합: 학교(4) + 학년(1) + 반(2) + 번호(2) = 9자리
            # 예: 001510305
            student_id = f"{school_code_str}{student.grade}{student.class_no:02d}{student.number:02d}"
            
            # 3. 계정 생성
            user, created = CustomUser.objects.get_or_create(
                username=student_id,
                defaults={
                    'name': student.name,
                    'password': make_password("1234"),
                    # 선택된 학교 객체를 직접 연결
                    'school_id': school_db_id, 
                    'is_active': True
                }
            )
            student.save() # 최종 저장
            messages.success(request, f"{student.name} 학생 등록 완료 (ID: {student_id})")
            return redirect('mypage')
        else:
            messages.error(request, "학교를 선택해주세요.")
    else:
        form = StudentForm()
    
    return render(request, 'accounts/student_form.html', {'form': form})

# 이메일 중복 체크 API
def check_email_duplicate(request):
    email = request.GET.get('email', None)
    data = {
        'is_taken': CustomUser.objects.filter(email=email).exists()
    }
    if data['is_taken']:
        data['error_message'] = '이미 사용 중인 이메일입니다.'
    return JsonResponse(data)