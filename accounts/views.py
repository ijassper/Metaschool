import requests
import random
import openai
import pandas as pd
import io
import json
import pandas as pd  # 엑셀 처리를 위해 필요
from django.db.models import Q  # 다중 필터 기능
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
from django.db import transaction   # 
from .forms import CustomUserCreationForm, StudentForm
from .models import Student, CustomUser, School  # Student, CustomUser, School 모델 모두 가져오기
from .models import SystemConfig, PromptCategory, PromptLengthOption, PromptTemplate
from .decorators import teacher_required    # 교사 전용 접근 제어 데코레이터
from activities.models import Activity  # 평가관리


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
    
    # 2. 학생일 경우: 선생님이 낸 평가 목록 가져오기
    if request.user.role == 'STUDENT':
        # 내 이메일로 Student 명부 찾기
        try:
             # 내 정보 찾기
            student_info = Student.objects.get(email=request.user.email)
            my_teacher = student_info.teacher
            
            # ★ [핵심] '나(student_info)'를 평가 대상으로 포함하고 있는 활동만 검색
            # (teacher=my_teacher 조건은 빼도 됩니다. 다른 선생님이 지정했을 수도 있으니까요)
            activities = Activity.objects.filter(
                target_students=student_info,  # 내가 대상자에 포함됨
                is_active=True                 # 평가 진행 중임
            ).order_by('-created_at')
            
            context['student_activities'] = activities
            context['my_teacher'] = my_teacher # 선생님 이름 표시용
            
        except Student.DoesNotExist:
            context['error_msg'] = "학생 명부에서 정보를 찾을 수 없습니다."

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

# 2. 마이페이지 뷰
@login_required
@teacher_required
def mypage(request):
    # 로그인한 선생님(request.user)이 담당하는 학생들만 가져오기
    my_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')
    
    return render(request, 'accounts/mypage.html', {'students': my_students})

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
            ai_model = body.get('ai_model', 'gpt-3.5-turbo') # ★ 모델 정보 받기
            
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
        
    return redirect('dashboard') # 또는 mypage

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