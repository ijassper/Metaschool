import openai
import pandas as pd
import io
import json
import pandas as pd  # 엑셀 처리를 위해 필요
from django.urls import reverse_lazy
from django.http import JsonResponse  # 검색 기능을 위해 필요
from django.http import HttpResponse
from django.views import generic
from django.shortcuts import render, redirect
from django.contrib.auth import login  # 자동 로그인을 위해 필요
from django.contrib.auth.decorators import login_required
from django.contrib import messages  # 알림 메시지(성공/실패)를 위해 필요
from django.contrib.auth.hashers import make_password  # 비밀번호 암호화
from .forms import CustomUserCreationForm, StudentForm
from .models import Student, CustomUser, School  # Student, CustomUser, School 모델 모두 가져오기
from .models import SystemConfig, PromptCategory, PromptLengthOption, PromptTemplate

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

# 1단계: 파일 업로드
@login_required
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
def ai_generator_step2(request):
    df_json = request.session.get('df_data')
    columns = request.session.get('df_columns')
    filename = request.session.get('uploaded_filename', '파일 없음') # ★ 파일명 가져오기

    if not df_json:
        messages.error(request, "파일 정보가 만료되었습니다. 다시 업로드해주세요.")
        return redirect('ai_generator_step1')
    
    # 카테고리 및 템플릿 데이터 구조화 (JSON 변환용) ---
    # 구조: { 대분류ID: { name: "대분류명", children: { 소분류ID: { name: "소분류명", templates: [템플릿들...] } } } }
    
    tree_data = {}
    # 부모가 없는 최상위 카테고리 가져오기 (대분류)
    main_categories = PromptCategory.objects.filter(parent__isnull=True)

    for main in main_categories:
        # 부모가 없는 최상위 카테고리 가져오기 (대분류)
        main_categories = PromptCategory.objects.filter(parent__isnull=True)
        
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
    }

    if request.method == 'POST':
        try:
            # 1. 설정값 가져오기
            selected_cols = request.POST.getlist('selected_cols')
            target_col_name = request.POST.get('target_col_name', 'AI_분석결과')
            temperature = float(request.POST.get('temperature', 0.7)) # ★ 온도 가져오기
            
            # 입력된 프롬프트 내용 가져오기 (p_length는 select 값이거나 직접 입력값)
            p_context = request.POST.get('p_context', '')
            p_role = request.POST.get('p_role', '')
            p_task = request.POST.get('p_task', '')
            p_example = request.POST.get('p_example', '')
            p_length = request.POST.get('p_length', '') # 셀렉트박스 값

            # 2. API 키 확인
            try:
                config = SystemConfig.objects.get(key_name='OPENAI_API_KEY')
                api_key = config.value
            except SystemConfig.DoesNotExist:
                # ★ 중요: 에러 발생 시 1단계로 튕기지 않고 현재 페이지에 메시지 띄우기
                messages.error(request, "관리자 설정 오류: OPENAI_API_KEY가 등록되지 않았습니다.")
                return render(request, 'accounts/ai_generator_step2.html', context) # context 사용

            # 3. AI 분석 실행
            client = openai.OpenAI(api_key=api_key)
            df = pd.read_json(df_json)
            ai_results = []

            for index, row in df.iterrows():
                # ★ 기능 2: '실행여부' 컬럼 확인 (값이 1이 아니면 건너뜀)
                # (컬럼명이 정확히 '실행여부'여야 함 / 없으면 모두 실행)
                if '실행여부' in df.columns:
                    val = str(row['실행여부']).strip().lower()
                    if val not in ['1', '1.0', 'true']:
                        ai_results.append("")
                        continue

                # 기초 자료 텍스트 생성
                context_parts = []
                # ★ 기능 3: 이름 컬럼이 선택되었다면 명확히 표기
                for col in selected_cols:
                    if col in row:
                        val = str(row[col])
                        if '이름' in col or 'name' in col.lower():
                            context_parts.append(f"[학생이름: {val}]")
                        else:
                            context_parts.append(f"{col}: {val}")
                
                context_text = " / ".join(context_parts)
                
                if not context_text.strip():
                    ai_results.append("")
                    continue
                
                # ★ 최종 프롬프트 조합 (입력받은 5개 항목 합치기)
                full_prompt = f"""
                [기초 데이터]
                {context_text}

                [프롬프트 맥락]
                {p_context}

                [당신의 역할]
                {p_role}

                [할 일]
                {p_task}

                [원하는 결과 예시]
                {p_example}

                [분량 및 형식]
                {p_length}
                """

                response = client.chat.completions.create(
                    model="gpt-4o", 
                    messages=[
                        {"role": "system", "content": "당신은 생활기록부 작성 전문가입니다."},
                        {"role": "user", "content": full_prompt}
                    ],
                    temperature=temperature
                )
                ai_results.append(response.choices[0].message.content)

            # 4. 결과 저장 및 다운로드
            df[target_col_name] = ai_results
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)

            # 원본 파일명 앞에 'Result_' 붙여서 다운로드
            download_filename = f"Result_{filename}"
            
            response = HttpResponse(
                output,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            # 한글 파일명 깨짐 방지 처리
            from urllib.parse import quote
            response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{quote(download_filename)}'

            # ★ 다운로드 완료 신호 (쿠키) 설정
            response.set_cookie('download_complete', 'true', max_age=10) 
            
            return response

        except Exception as e:
            # ★ 에러 발생 시 이유를 명확히 보여줌
            messages.error(request, f"오류 발생: {str(e)}")
            # 오류가 나도 1단계로 튕기지 않게 함
            return render(request, 'accounts/ai_generator_step2.html', context) # context 사용

    # GET 요청 시 템플릿 전달
    return render(request, 'accounts/ai_generator_step2.html', context)