from django.db.models import Q  # 다중 필터 기능
from django.urls import reverse_lazy
from django.http import JsonResponse  # 검색 기능을 위해 필요
from django.http import HttpResponse
from django.views import generic
from django.views.decorators.csrf import csrf_exempt    # API 뷰에서 CSRF 예외 처리를 위해 필요
from django.shortcuts import render, redirect, get_object_or_404 # 리다이렉트 및 객체 가져오기
from django.contrib.auth import login, update_session_auth_hash  # 자동 로그인을 위해 필요, 비밀번호 변경 후 세션 유지 위해 필요
from django.contrib.auth.decorators import login_required
from django.contrib import messages  # 알림 메시지(성공/실패)를 위해 필요
from django.contrib.auth.hashers import make_password  # 비밀번호 암호화
from django.db import transaction   # 트랜잭션 처리를 위해 필요
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm    # 로그인 폼 (필요 시 사용), 비밀번호 변경 폼
from django.contrib.auth import authenticate,login as auth_login # 로그인 처리 함수 (회원가입 후 자동 로그인 위해 필요)
import requests
import random
from activities.views import get_form_config
import openai
import pandas as pd
import io
import json
import pandas as pd  # 엑셀 처리를 위해 필요
from .forms import CustomUserCreationForm, StudentForm, UserUpdateForm, CustomAuthenticationForm  # 회원가입 폼, 학생 등록 폼, 사용자 정보 수정 폼, 로그인 폼
from .models import CustomUser, School  # CustomUser, School 모델 모두 가져오기
from .models import SystemConfig, PromptCategory, PromptLengthOption, PromptTemplate # AI 생성기 관련 모델 가져오기
from .decorators import teacher_required    # 교사 전용 접근 제어 데코레이터
from activities.models import Activity, Student, Answer  # 평가관리, 학생, 답안 모델 가져오기

# 로그인 유지 기능이 포함된 커스텀 로그인 함수
def login_view(request):
    # 이미 로그인된 상태라면 대시보드로 보냄
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        # 1. 폼에서 아이디(username)와 비번(password) 가져오기
        username = request.POST.get('username')
        password = request.POST.get('password')
        # login.html의 <input type="checkbox" name="remember_me"> 확인
        remember_me = request.POST.get('remember_me')
        login_type = request.POST.get('login_type') # 'teacher' 또는 'student' 가져오기

        # 2. 아이디가 DB에 존재하는지 먼저 확인
        user_exists = CustomUser.objects.filter(username=username).exists()

        # 3. 실제 인증 시도
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # [성공 시 추가 검증] 선택한 탭(login_type)과 실제 계정 권한(user.role) 비교
            
            # (A) 학생 탭인데 교사/관리자 계정인 경우
            if login_type == 'student' and user.role in ['TEACHER', 'LEADER']:
                return render(request, 'registration/login.html', {
                    'error_message': "이 계정은 [선생님] 전용 계정입니다.<br>'교사' 탭을 선택 후 로그인해 주세요.",
                    'error_code': "ROLE_MISMATCH_TEACHER",
                    'login_type': login_type    # 선택한 탭 정보도 함께 보내서 탭 유지
                })
            
            # (B) 교사 탭인데 학생 계정인 경우
            elif login_type == 'teacher' and user.role == 'STUDENT':
                return render(request, 'registration/login.html', {
                    'error_message': "이 계정은 [학생] 전용 계정입니다.<br>'학생' 탭을 선택 후 로그인해 주세요.",
                    'error_code': "ROLE_MISMATCH_STUDENT",
                    'login_type': login_type    # 선택한 탭 정보도 함께 보내서 탭 유지
                })
            
            # (C) 모든 검증 통과 시 로그인 처리
            auth_login(request, user) # 실제 로그인 수행
            
            # --- [로그인 유지 로직 시작] ---
            if remember_me:
                # 체크박스 선택 시: 2주(1,209,600초) 동안 세션 유지
                request.session.set_expiry(1209600)
            else:
                # 선택 안 할 시: 브라우저를 닫으면 로그아웃
                request.session.set_expiry(0)
            # --- [로그인 유지 로직 끝] ---
            
            return redirect('dashboard')
        else:
            # [인증 실패 로직] 원인 분석 로직
            if user_exists:
                # 아이디는 있는데 인증에 실패했다면? -> 비밀번호가 틀린 것
                error_message = "비밀번호가 일치하지 않습니다. 다시 확인해 주세요."
                error_code = "INVALID_PASSWORD"
            else:
                # 아이디 자체가 없다면?
                error_message = "존재하지 않는 아이디입니다. 회원가입을 먼저 진행해 주세요."
                error_code = "USER_NOT_FOUND"
            
            # 템플릿에 에러 메시지와 코드를 보냄
            return render(request, 'registration/login.html', {
                'error_message': error_message,
                'error_code': error_code,
                'login_type': login_type    # 선택한 탭 정보도 함께 보내서 탭 유지
            })
    else:
        form = CustomAuthenticationForm()
    
    # login.html 템플릿을 사용하여 로그인 화면을 보여줌
    return render(request, 'registration/login.html', {'form': form})

# 대시보드 (로그인 후 첫 화면)
@login_required
def dashboard(request):
    # 로그인한 사용자 정보 가져오기
    user = request.user
    context = {}
    print(f"--- DASHBOARD 진입: {user.name} (Role: {user.role}) ---", flush=True)
    # ---- 학생(STUDENT) 로직 ----
    if user.role == 'STUDENT':
        print(f"DEBUG: {user.name}님은 학생 로직으로 진입합니다.", flush=True)
        student_profile = Student.objects.filter(email=user.email).first()
                
        if not student_profile:
            student_profile = getattr(user, 'student', None)

        if student_profile:
            # 나에게 배정된 모든 활성화된 평가 (전체 리스트용)
            base_query = Activity.objects.filter(target_students=student_profile, is_active=True).order_by('-created_at')
            
            # 완료된 개수를 세기 위한 변수 초기화
            completed_count = 0 

            # 전체 리스트에 대해서도 제출 여부 체크
            for activity in base_query:
                # 모델에 추가한 함수를 사용하여 답변 객체 가져오기
                ans = activity.get_student_answer(student_profile)
                activity.my_answer = ans # [추가] 이 객체가 있어야 템플릿에서 '작성 중' 판단 가능
                
                # 제출 여부 판단 (제출 시간이 기록되어 있어야 함)
                activity.has_submitted = bool(ans and ans.submitted_at)

                # 제출 완료된 경우 카운트 증가
                if activity.has_submitted:
                    completed_count += 1
            
            # 교사용과 동일하게 카테고리별로 묶기
            category_blocks = []
            seen_categories = []
            for act in base_query:
                cat_code = act.category.strip()
                if cat_code not in seen_categories:
                    seen_categories.append(cat_code)
                    category_blocks.append({
                        'name': act.get_category_display(),
                        'items': [a for a in base_query if a.category.strip() == cat_code]
                    })

            context.update({
                'student': student_profile,  # student 라는 이름으로 객체 전달
                'category_blocks': category_blocks, # 묶인 데이터
                'activities': base_query,           # 전체 카운트용
                'completed_count': completed_count, # 완료된 개수
                'ongoing_count': base_query.count() - completed_count # 진행 중 개수 계산
            })

        # 학생 전용 템플릿 반환
        return render(request, 'activities/student_dashboard.html', context)
    
    # 2. 교사/대표 공통 로직 시작 (TEACHER와 LEADER 모두 진입)
    if user.role in ['LEADER', 'TEACHER']:

        print(f"DEBUG: {user.name}님은 교사 로직으로 진입합니다.", flush=True)
        # [2-1] 학교 대표(LEADER) 전용 데이터만 처리
        if user.role == 'LEADER' and user.school:
            guest_teachers = CustomUser.objects.filter(school=user.school, role='GUEST')
            school_students = Student.objects.filter(teacher__school=user.school)        
            context['guest_teachers'] = guest_teachers
            context['school_students'] = school_students
            context['student_count'] = school_students.count()

        # [2-2] 모든 교사 공통: 5개(7개) 블록 생성 로직
        # 1. 선생님이 만든 모든 활동을 최신순으로 가져옴
        my_activities = Activity.objects.filter(teacher=user).order_by('-created_at')

        # 2. 활동이 존재하는 카테고리들을 순서대로 추출 (최대 5개)
        category_blocks = []
        seen_categories = []

        for act in my_activities:
            clean_cat = act.category.strip()
            if clean_cat not in seen_categories:
                if len(seen_categories) < 7: # 7개로 확장 권장
                    seen_categories.append(clean_cat)
                    # 해당 카테고리의 아이템들을 가져온 후, 각각 config를 심어줍니다.
                    items = my_activities.filter(category__icontains=clean_cat)
                    for item in items:
                        item.form_config = get_form_config(item.sub_category)
                    
                    category_blocks.append({
                        'name': act.get_category_display(),
                        'items': items # config가 포함된 items를 넣습니다.
                    })
        context['category_blocks'] = category_blocks

        # 교사 전용 대시보드 반환
        return render(request, 'dashboard.html', context)

    # 3. 그 외 권한 (관리자 등)
    print(f"DEBUG: {user.name}님은 예외 상황입니다. Role: {user.role}", flush=True)
    return render(request, 'dashboard.html', context)

# 1. 회원가입 뷰 (수정됨: 가입 후 자동 로그인 & 마이페이지 이동)
class SignUpView(generic.CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('dashboard')  # 가입 성공 시 이동할 곳
    template_name = 'registration/signup.html'

    def form_valid(self, form):
        # 회원가입 정보 저장
        response = super().form_valid(form)
        # 저장된 유저 정보로 즉시 로그인 처리
        user = self.object
        login(self.request, user)
        return response

# 학생 개별 등록 페이지
@login_required
@teacher_required
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        # (학교 코드 받는 로직 삭제함)

        if form.is_valid():
            student = form.save(commit=False)
            student.teacher = request.user
            
            # 입력받은 이메일을 아이디로 사용
            student_email = form.cleaned_data['email']
            
            # 비밀번호 규칙
            student_code = f"{student.grade}{student.class_no:02d}{student.number:02d}"
            password_raw = f"s{student_code}!@"
            
            # 계정 생성
            user, created = CustomUser.objects.get_or_create(
                username=student_email, # ★ 아이디 = 이메일
                defaults={
                    'name': student.name,
                    'email': student_email,
                    'password': make_password(password_raw),
                    'school': request.user.school,
                    'role': 'STUDENT',
                    'is_active': True
                }
            )
            
            student.save()
            messages.success(request, f"{student.name} 학생 등록 완료")
            return redirect('student_list')
    else:
        form = StudentForm()
    
    return render(request, 'accounts/student_form.html', {'form': form})

# 2. 정보수정
@login_required
def profile_settings(request):
    user = request.user
    # 학생이면 무조건 보안(비밀번호) 탭으로 고정, 교사는 URL 파라미터 따름
    if user.role == 'STUDENT':
        active_tab = 'security'
    else:
        active_tab = request.GET.get('tab', 'profile')
    
    if request.method == 'POST':
        # 1. 정보 수정 (교사 전용)
        if 'update_profile' in request.POST and user.role != 'STUDENT':
            profile_form = UserUpdateForm(request.POST, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "정보가 수정되었습니다.")
                return redirect('/accounts/profile-settings/?tab=profile')

        # 2. 비밀번호 변경 (공통)
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user) # 세션 유지
                messages.success(request, "비밀번호가 변경되었습니다.")
                # 이동 후에도 탭 유지
                return redirect(f'/accounts/profile-settings/?tab=security')
            else:
                active_tab = 'security'
    
    # GET 요청 시 폼 초기화
    profile_form = UserUpdateForm(instance=user) if user.role != 'STUDENT' else None
    password_form = PasswordChangeForm(user)

    return render(request, 'accounts/profile_settings.html', {
        'profile_form': profile_form,
        'password_form': password_form,
        'active_tab': active_tab,
    })

@login_required
@teacher_required
def student_list(request):
    # 1. 내 학생들 전체 가져오기 (기본)
    all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')

    # 2. 필터용 계층 데이터 만들기 (학년 -> 반)
    # (activity_result와 동일한 안전한 로직 사용)
    temp_data = {}
    for s in all_students:
        g = s.grade
        c = s.class_no
        if g not in temp_data: temp_data[g] = []
        if c not in temp_data[g]: temp_data[g].append(c)
    
    filter_data = []
    for g in sorted(temp_data.keys()):
        filter_data.append({
            'grade': g,
            'classes': sorted(list(set(temp_data[g])))
        })

    # 3. 검색 조건 가져오기
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')

    # 4. 초기 진입 시 기본값 설정 (1학년 1반)
    # (검색어도 없고, 선택도 안 했을 때 데이터가 너무 많으면 느리므로 첫 반만 보여줌)
    if not selected_targets and not name_query:
        if filter_data:
            g = filter_data[0]['grade']
            c = filter_data[0]['classes'][0]
            selected_targets = [f"{g}_{c}"]

    # 5. 필터링 적용
    students = all_students

    if selected_targets:
        q_objects = Q()
        for t in selected_targets:
            if '_' in t:
                g, c = t.split('_')
                q_objects |= Q(grade=g, class_no=c)
        students = students.filter(q_objects)

    if name_query:
        students = students.filter(name__contains=name_query)

    context = {
        'students': students,
        'filter_data': filter_data,       # ★ 트리 데이터 전달
        'selected_targets': selected_targets, # ★ 선택 상태 유지
        'current_q': name_query,
    }
    
    return render(request, 'accounts/student_list.html', context)

# 3. 엑셀 일괄 등록 뷰
@login_required
@teacher_required
def student_upload(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            df = pd.read_excel(excel_file)
            
            # 교사의 학교 정보 확인
            if not request.user.school:
                messages.error(request, "선생님의 소속 학교 정보가 없습니다. 관리자에게 문의하세요.")
                return redirect('student_list')

            count = 0
            
            # 트랜잭션으로 속도 향상 및 안전성 확보
            with transaction.atomic():
                for index, row in df.iterrows():
                    # 1. 엑셀 데이터 추출
                    grade = int(row['학년'])
                    class_no = int(row['반'])
                    number = int(row['번호'])
                    name = str(row['이름'])
                    
                    # ★ [핵심] 엑셀의 '이메일(ID)' 컬럼 읽기 (공백 제거)
                    # (엑셀 파일 헤더가 반드시 '이메일(ID)' 여야 합니다)
                    email = str(row['이메일(ID)']).strip()

                    # 이메일이 없거나 비어있으면 건너뜀
                    if not email or email == 'nan':
                        continue

                    # 2. 비밀번호 생성 규칙: s + 학번 + !@ (예: s10101!@)
                    student_code = f"{grade}{class_no:02d}{number:02d}"
                    password_raw = f"s{student_code}!@"

                    # 3. 학생 계정(User) 생성
                    # ★ 아이디(username)를 이메일로 설정
                    user, created = CustomUser.objects.get_or_create(
                        username=email, 
                        defaults={
                            'name': name,
                            'email': email,
                            'password': make_password(password_raw),
                            'school': request.user.school,
                            'role': 'STUDENT',
                            'is_active': True
                        }
                    )
                    
                    # 4. 학생 명부(Student) 저장
                    # ★ Student 테이블에도 email을 저장해야 명렬표에 나옵니다.
                    Student.objects.update_or_create(
                        teacher=request.user,
                        grade=grade, 
                        class_no=class_no, 
                        number=number,
                        defaults={
                            'name': name,
                            'email': email 
                        }
                    )
                    count += 1
            
            messages.success(request, f"{count}명의 학생이 성공적으로 등록되었습니다!")

        except KeyError as e:
             messages.error(request, f"엑셀 파일 양식이 틀렸습니다. '{str(e)}' 컬럼이 있는지 확인해주세요.")
        except Exception as e:
            messages.error(request, f"오류 발생: {str(e)}")
    
    return redirect('student_list')

# 학교 검색 API (AJAX 요청 처리)
def search_school(request):
    query = request.GET.get('q', '') # 검색어 가져오기
    if query:
        # 이름에 검색어가 포함된 학교 찾기 (최대 30개만)
        schools = School.objects.filter(name__contains=query)[:30]
        results = [{'id': s.id, 'name': s.name, 'office': s.office} for s in schools]
    else:
        results = []
    return JsonResponse({'results': results})



# 이메일 중복 체크 API
def check_email_duplicate(request):
    email = request.GET.get('email', None)
    data = {
        'is_taken': CustomUser.objects.filter(email=email).exists()
    }
    if data['is_taken']:
        data['error_message'] = '이미 사용 중인 이메일입니다.'
    return JsonResponse(data)

# 1단계: 파일 업로드
@login_required
@teacher_required
def ai_generator_step1(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            # 엑셀 읽기
            df = pd.read_excel(excel_file)
            
            # 세션에 데이터 및 파일명 저장
            request.session['df_data'] = df.to_json()
            request.session['df_columns'] = df.columns.tolist()
            request.session['uploaded_filename'] = excel_file.name # ★ 파일명 저장
            
            return redirect('ai_generator_step2')
        except Exception as e:
            messages.error(request, f"파일 읽기 실패: {str(e)}")
            
    return render(request, 'accounts/ai_generator_step1.html')

# 2단계: 설정 및 실행
@login_required
@teacher_required
def ai_generator_step2(request):
    df_json = request.session.get('df_data')
    columns = request.session.get('df_columns')
    filename = request.session.get('uploaded_filename', '파일 없음') # ★ 파일명 가져오기

    if not df_json:
        messages.error(request, "파일 정보가 만료되었습니다. 다시 업로드해주세요.")
        return redirect('ai_generator_step1')
    
    # 2. [필수] 전체 데이터 개수 세기 (진행률 바 표시용)
    try:
        df = pd.read_json(df_json)
        total_rows = len(df) # ★ 전체 학생 수
    except:
        total_rows = 0
    
    # 카테고리 및 템플릿 데이터 구조화 (JSON 변환용) ---
    # 구조: { 대분류ID: { name: "대분류명", children: { 소분류ID: { name: "소분류명", templates: [템플릿들...] } } } }
    
    tree_data = {}
    # 부모가 없는 최상위 카테고리 가져오기 (대분류)
    main_categories = PromptCategory.objects.filter(parent__isnull=True)

    for main in main_categories:
        # 대분류의 자식들 (소분류)
        sub_cats = PromptCategory.objects.filter(parent=main)
        
        children_data = {}
        has_content = False # 내용물이 있는지 체크
        
        for sub in sub_cats:
            # 소분류에 연결된 템플릿들
            templates = PromptTemplate.objects.filter(category=sub)
            
            # 템플릿이 하나라도 있으면 목록 생성
            if templates.exists():
                has_content = True
                temp_list = []
                for t in templates:
                    # 분량 옵션 값 처리
                    len_val = ""
                    if t.length_option:
                        len_val = t.length_option.value
                    
                    temp_list.append({
                        'id': t.id,
                        'title': t.title,
                        'description': t.description,   # 사용 가이드
                        'context': t.context,
                        'task': t.task,
                        'example': t.output_example,
                        'length': len_val   # 분량 옵션 값
                    })
                
                children_data[sub.id] = {
                    'name': sub.name,
                    'templates': temp_list
                }
        
        # 소분류가 하나라도 있거나, 템플릿이 있는 경우에만 트리에 추가
        if children_data: 
            tree_data[main.id] = {
                'name': main.name,
                'children': children_data
            }

    # 분량 옵션 리스트
    length_options = PromptLengthOption.objects.all()
    
    # [공통 데이터 묶음] - 화면에 보낼 재료들
    context = {
        'columns': columns,
        'filename': filename,
        'tree_data_json': json.dumps(tree_data), # JSON으로 변환해서 전달
        'length_options': length_options,
        'total_rows': total_rows,  # ★ [필수 추가] 전체 행 개수
    }

    # POST 요청(분석 실행)은 이제 JavaScript(API)가 하므로, 
    # 여기서는 무조건 화면(HTML)만 보여주면 됩니다.
    return render(request, 'accounts/ai_generator_step2.html', context)

def call_openai_api(api_key, model, prompt_system, prompt_user, temperature=0.7):
    """
    OpenAI API를 직접 호출하는 헬퍼 함수
    """
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": prompt_user}
        ],
        "temperature": temperature
    }
    
    # 가비아 환경의 특성을 고려해 timeout 60초 설정
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        # 에러 발생 시 로그를 남김
        error_msg = response.json().get('error', {}).get('message', '알 수 없는 에러')
        print(f"DEBUG: OpenAI API Error ({response.status_code}): {error_msg}")
        raise Exception(f"AI 응답 실패: {error_msg}")
    
# 1명씩 처리하는 API (JavaScript가 호출함)
@csrf_exempt
@login_required
def api_process_one_row(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            row_index = body.get('index')
            selected_cols = body.get('selected_cols')
            prompt_system = body.get('prompt_system')
            temperature = float(body.get('temperature', 0.7))
            ai_model = body.get('ai_model', 'gpt-4o-mini') # ★ 모델 정보 받기
            
            # 세션에서 데이터 원본 가져오기
            df_json = request.session.get('df_data')
            df = pd.read_json(df_json)
            
            # 해당 행(Row) 데이터 가져오기
            row = df.iloc[row_index]
            
            # 실행여부 체크
            if '실행여부' in df.columns:
                val = str(row['실행여부']).strip().lower()
                if val not in ['1', '1.0', 'true']:
                    return JsonResponse({'status': 'skip', 'result': ''})

            # 프롬프트 재료 조합
            context_parts = []
            for col in selected_cols:
                if col in row:
                    val = str(row[col])
                    if '이름' in col or 'name' in col.lower():
                        context_parts.append(f"[학생이름: {val}]")
                    else:
                        context_parts.append(f"{col}: {val}")
            
            context_text = " / ".join(context_parts)
            
            final_prompt = f"[기초자료]\n{context_text}\n\n[지시사항]\n{prompt_system}"
            result_text = ""

            # ---------------------------------------------------------
            # [분기 1] OpenAI GPT 사용
            # ---------------------------------------------------------
            if ai_model.startswith('gpt'):
                # 1. 키 가져오기 (멀티 키 지원)
                config = SystemConfig.objects.get(key_name='OPENAI_API_KEY')
                api_keys_list = [k.strip() for k in config.value.split(',') if k.strip()]
                
                if not api_keys_list:
                    return JsonResponse({'status': 'error', 'message': 'OpenAI API 키가 없습니다.'})
            
                selected_key = random.choice(api_keys_list) # 랜덤 키 선택

                # 2. [변경 포인트] 라이브러리 대신 직접 만든 call_openai_api 함수 호출
                try:
                    result_text = call_openai_api(
                        api_key=selected_key,
                        model=ai_model,
                        prompt_system="당신은 생활기록부 전문가입니다.", # 시스템 역할
                        prompt_user=final_prompt,                      # 조합된 데이터 + 지시사항
                        temperature=temperature
                    )
                except Exception as api_err:
                    print(f"DEBUG: OpenAI API Call Failed - {str(api_err)}")
                    return JsonResponse({'status': 'error', 'message': f'API 호출 에러: {str(api_err)}'})

            # ---------------------------------------------------------
            # [분기 2] Google Gemini 사용 (신규)
            # ---------------------------------------------------------
            elif ai_model.startswith('gemini'):
                try:
                    config = SystemConfig.objects.get(key_name='GOOGLE_API_KEY')
                    api_key = config.value
                    
                    # Gemini API 주소 (REST API)
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{ai_model}:generateContent?key={api_key}"
                    
                     # 보낼 데이터 포장
                    payload = {
                        "contents": [{
                            "parts": [{"text": f"당신은 생활기록부 전문가입니다.\n{final_prompt}"}]
                        }],
                        "generationConfig": {
                            "temperature": temperature
                        }
                    }
                    
                    # 직접 전송 (requests 사용)
                    response = requests.post(url, json=payload)
                    response_data = response.json()
                    
                    # 결과 추출
                    if "candidates" in response_data:
                        result_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        # 에러 발생 시 구글이 보낸 메시지 확인
                        result_text = f"[Google 오류] {response_data}"
                        
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': f'통신 오류: {str(e)}'})

            return JsonResponse({'status': 'success', 'result': result_text})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'fail'}, status=400)


# 최종 결과 엑셀 다운로드 API
@csrf_exempt
@login_required
def api_download_excel(request):
    if request.method == 'POST':
        try:
            ## 1. 전달된 결과 데이터 확인
            results_json = request.POST.get('results')
            target_col = request.POST.get('target_col_name', 'AI_결과')
            
            if not results_json:
                return HttpResponse("결과 데이터가 없습니다.", status=400)

            results = json.loads(results_json)
            
            # 2. 세션에서 원본 데이터 복구
            df_json = request.session.get('df_data')
            if not df_json:
                return HttpResponse("세션이 만료되었습니다. 다시 시도해주세요.", status=400)
            
            df = pd.read_json(df_json)
            
            # 3. 데이터 개수 맞춤 확인 (매우 중요)
            # 만약 결과 개수와 엑셀 행 수가 다르면 에러가 날 수 있으므로 보정
            if len(results) < len(df):
                results.extend([''] * (len(df) - len(results)))
            elif len(results) > len(df):
                results = results[:len(df)]

            # 4. 결과 열 추가
            df[target_col] = results
            
            # 5. 엑셀 파일 생성 (안전한 방식)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)
            
            uploaded_filename = request.session.get('uploaded_filename', 'result.xlsx')
            download_filename = f"Result_{uploaded_filename}"
            
            response = HttpResponse(
                output.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
            from urllib.parse import quote
            response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{quote(download_filename)}'
            return response
            
        except Exception as e:
            # 에러 발생 시 로그에 상세 내용 출력
            import traceback
            print(traceback.format_exc())
            return HttpResponse(f"엑셀 생성 중 서버 오류: {str(e)}", status=500)
        
# 게스트 교사 승인하기 (학교 대표 전용)
@login_required
def approve_teacher(request, user_id):
    # 승인 대상 교사 찾기
    target_user = get_object_or_404(CustomUser, id=user_id)
    
    # [보안 검사]
    # 1. 요청한 사람이 '학교 대표(LEADER)'인가?
    # 2. 요청한 사람과 대상 교사가 '같은 학교'인가?
    if request.user.role == 'LEADER' and request.user.school == target_user.school:
        target_user.role = 'TEACHER' # 일반 교사로 승급
        target_user.save()
        messages.success(request, f"{target_user.name} 선생님을 승인했습니다.")
    else:
        messages.error(request, "권한이 없거나 다른 학교 선생님입니다.")
    
    return redirect('dashboard')

# 비밀번호 초기화 로직
@login_required
@teacher_required
def reset_student_password(request, student_id):
    try:
        # 학생 찾기
        student = Student.objects.get(id=student_id, teacher=request.user)
        
        # User 계정 찾기 (학생 명부와 이름/학년/반이 일치하는 유저)
        # (주의: 이메일 기반이라 Student 모델과 User 모델 연결이 약할 수 있음.
        #  가장 정확한 건 Student 모델에 user 필드(OneToOne)를 두는 것이지만,
        #  지금 구조에서는 이름과 학교로 찾아야 함)
        
        target_users = CustomUser.objects.filter(
            name=student.name, 
            school=request.user.school,
            role='STUDENT'
        )
        
        # 동명이인이 있을 수 있으므로 주의 필요하지만, 일단 첫 번째 매칭
        if target_users.exists():
            user = target_users.first()
            
            # 초기화 규칙: s + 학번 + !@
            student_code = f"{student.grade}{student.class_no:02d}{student.number:02d}"
            new_pw = f"s{student_code}!@"
            
            user.set_password(new_pw)
            user.save()
            messages.success(request, f"{student.name} 학생 비밀번호 초기화 완료: {new_pw}")
        else:
            messages.error(request, "해당 학생의 계정을 찾을 수 없습니다.")

    except Exception as e:
        messages.error(request, f"오류: {str(e)}")
        
    return redirect('dashboard')

# 학생 삭제
@login_required
@teacher_required
def student_delete(request, student_id):
    try:
        # 1. 지울 학생 명부 찾기 (내 학생인지 확인)
        student = Student.objects.get(id=student_id, teacher=request.user)
        target_email = student.email
        student_name = student.name
        
        # 2. 명부(Student)에서 먼저 삭제
        student.delete()
        
        # 3. 로그인 계정(User) 찾아서 삭제
        # (이메일이 일치하고, 학생 권한인 계정만 삭제)
        if target_email:
            user_to_delete = CustomUser.objects.filter(
                email=target_email, 
                role='STUDENT'
            )
            if user_to_delete.exists():
                user_to_delete.delete()
                
        messages.success(request, f"{student_name} 학생의 정보와 계정을 모두 삭제했습니다.")
        
    except Student.DoesNotExist:
        messages.error(request, "학생을 찾을 수 없거나 권한이 없습니다.")
    except Exception as e:
        messages.error(request, f"삭제 중 오류 발생: {str(e)}")
        
    return redirect('student_list')

@login_required
def profile_update(request):
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "회원 정보가 수정되었습니다.")
            return redirect('dashboard')
    else:
        form = UserUpdateForm(instance=request.user)
    return render(request, 'accounts/profile_update.html', {'form': form})