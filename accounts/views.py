import random
import openai
import google.generativeai as genai
import pandas as pd
import io
import json
import pandas as pd  # 엑셀 처리를 위해 필요
from django.urls import reverse_lazy
from django.http import JsonResponse  # 검색 기능을 위해 필요
from django.http import HttpResponse
from django.views import generic
from django.views.decorators.csrf import csrf_exempt    # API 뷰에서 CSRF 예외 처리를 위해 필요
from django.shortcuts import render, redirect, get_object_or_404 # 리다이렉트 및 객체 가져오기
from django.contrib.auth import login  # 자동 로그인을 위해 필요
from django.contrib.auth.decorators import login_required
from django.contrib import messages  # 알림 메시지(성공/실패)를 위해 필요
from django.contrib.auth.hashers import make_password  # 비밀번호 암호화
from .forms import CustomUserCreationForm, StudentForm
from .models import Student, CustomUser, School  # Student, CustomUser, School 모델 모두 가져오기
from .models import SystemConfig, PromptCategory, PromptLengthOption, PromptTemplate
from .decorators import teacher_required    # 교사 전용 접근 제어 데코레이터

# 대시보드 (로그인 후 첫 화면)
@login_required
def dashboard(request):
    context = {}
    
    # 학교 대표(LEADER)일 경우, 우리 학교 정보 가져오기
    if request.user.role == 'LEADER' and request.user.school:
        # 1. 승인 대기 중인 우리 학교 게스트 교사들
        guest_teachers = CustomUser.objects.filter(
            school=request.user.school, 
            role='GUEST'
        )
        
        # 2. 우리 학교 전체 학생 수 (또는 명단)
        # teacher__school 로 검색해서 우리 학교 선생님들이 등록한 모든 학생을 찾음
        school_students = Student.objects.filter(teacher__school=request.user.school)
        
        context['guest_teachers'] = guest_teachers
        context['school_students'] = school_students
        context['student_count'] = school_students.count()

    return render(request, 'dashboard.html', context)

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

# 학생 개별 등록 페이지
@login_required
@teacher_required
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
                    'school': request.user.school,  # 선택된 학교 객체를 직접 연결
                    'role': 'STUDENT',  # ★ 학생 등급 강제 부여
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

# 2. 마이페이지 뷰
@login_required
@teacher_required
def mypage(request):
    # 로그인한 선생님(request.user)이 담당하는 학생들만 가져오기
    my_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')
    
    return render(request, 'accounts/mypage.html', {'students': my_students})

# 3. 엑셀 일괄 등록 뷰
@login_required
@teacher_required
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
                        'school': request.user.school,  # 교사의 학교 정보 상속
                        'role': 'STUDENT', # ★ 학생 등급 강제 부여
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
                        'role': t.role,
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

# [신규] 1명씩 처리하는 API (JavaScript가 호출함)
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
            ai_model = body.get('ai_model', 'gpt-4o') # ★ 모델 정보 받기
            
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
                # 키 가져오기 (멀티 키 지원)
                config = SystemConfig.objects.get(key_name='OPENAI_API_KEY')
                api_keys_list = [k.strip() for k in config.value.split(',') if k.strip()]
                
                if not api_keys_list:
                    return JsonResponse({'status': 'error', 'message': 'OpenAI API 키가 없습니다.'})
                
                import random
                client = openai.OpenAI(api_key=random.choice(api_keys_list))
                
                response = client.chat.completions.create(
                    model=ai_model,
                    messages=[
                        {"role": "system", "content": "당신은 생활기록부 전문가입니다."},
                        {"role": "user", "content": final_prompt}
                    ],
                    temperature=temperature
                )
                result_text = response.choices[0].message.content

            # ---------------------------------------------------------
            # [분기 2] Google Gemini 사용 (신규)
            # ---------------------------------------------------------
            elif ai_model.startswith('gemini'):
                try:
                    config = SystemConfig.objects.get(key_name='GOOGLE_API_KEY')
                    genai.configure(api_key=config.value)
                    
                    # Gemini 모델 설정
                    model = genai.GenerativeModel(ai_model)
                    
                    # Gemini 설정 (Temperature 등)
                    generation_config = genai.types.GenerationConfig(
                        temperature=temperature
                    )
                    
                    # Gemini 호출 (시스템 프롬프트가 따로 없어서 합쳐서 보냄)
                    full_msg = f"당신은 생활기록부 전문가입니다.\n{final_prompt}"
                    response = model.generate_content(full_msg, generation_config=generation_config)
                    result_text = response.text
                    
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': f'Google API 오류: {str(e)}'})

            return JsonResponse({'status': 'success', 'result': result_text})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'fail'}, status=400)


# [신규] 최종 결과 엑셀 다운로드 API
@csrf_exempt
@login_required
def api_download_excel(request):
    if request.method == 'POST':
        try:
            # 프론트엔드에서 완성된 결과 리스트를 받음
            results = json.loads(request.POST.get('results'))
            target_col = request.POST.get('target_col_name')
            
            # 원본 데이터 로드
            df = pd.read_json(request.session.get('df_data'))
            filename = request.session.get('uploaded_filename', 'result.xlsx')

            # 결과 열 추가 (순서대로)
            # (주의: 건너뛴 행은 빈칸으로 채워져 있어야 순서가 맞음)
            df[target_col] = results
            
            # 엑셀 생성
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)
            
            download_filename = f"Result_{filename}"
            response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            from urllib.parse import quote
            response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{quote(download_filename)}'
            return response
            
        except Exception as e:
            return HttpResponse(f"엑셀 생성 오류: {str(e)}", status=500)
        
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