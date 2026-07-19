# AI 분석 및 프롬프트 (activity_analysis, api_process_db_row 등)

import json
import requests
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Value, F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 커스텀 데코레이터 및 계정 모델 임포트
from accounts.decorators import teacher_required
from accounts.models import Student, SystemConfig, PromptTemplate, PromptLengthOption
from ..models import Activity, Question, Answer, AnalysisResult
from .main_views import get_accessible_students, get_student_tree

FORCED_AI_ANALYSIS_MODEL = 'gpt-4o-mini'

# [1] 결과 분석 페이지 (활동별)
@login_required
@teacher_required
def activity_analysis(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    question = activity.questions.first() # 현재는 단일 문항 가정

    # 1. 평가 대상 학생 가져오기 (지정된 학생만)
    all_students = activity.target_students.all().order_by('grade', 'class_no', 'number')
    
    # 대상이 없으면 선생님 전체 학생으로 대체 (호환성)
    if not all_students.exists():
        all_students = get_accessible_students(request.user)

    # 2. 필터 데이터 생성 (학년/반 트리)
    temp_dict = {}
    for s in all_students:
        g = s.grade
        c = s.class_no
        if g not in temp_dict: temp_dict[g] = []
        if c not in temp_dict[g]: temp_dict[g].append(c)
    
    filter_data = []
    for g in sorted(temp_dict.keys()):
        filter_data.append({'grade': g, 'classes': sorted(list(set(temp_dict[g])))})

    # 3. 검색 조건 처리
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')

    # 4. [최적화] 초기 진입 시 '1학년 1반' 강제 선택
    if not selected_targets and not name_query:
        if filter_data:
            g = filter_data[0]['grade']
            c = filter_data[0]['classes'][0]
            selected_targets = [f"{g}_{c}"]

    # 5. 필터링 적용
    target_students = all_students
    if selected_targets:
        q_objects = Q()
        for t in selected_targets:
            try:
                g, c = t.split('_')
                q_objects |= Q(grade=g, class_no=c)
            except: pass
        target_students = target_students.filter(q_objects)

    if name_query:
        target_students = target_students.filter(name__contains=name_query)

    # 6. 분석용 데이터 리스트 생성 (processed_data 구조)
    # (제출 현황과 달리, 여기서는 '답안 내용'과 '모든 분석 결과'가 중요합니다)
    
    # 가장 기본적이고 확실한 방식: 활동에 속한 모든 분석 결과 가져오기
    print(f"DEBUG: 활동 ID: {activity.id}, 질문 ID: {question.id}")
    
    # 해당 활동의 모든 AnalysisResult를 직접 조회
    all_analysis_results = AnalysisResult.objects.filter(
        answer__question__activity=activity
    ).select_related('answer', 'answer__student').order_by('created_at')
    
    print(f"DEBUG: 전체 분석 결과 수: {all_analysis_results.count()}")
    
    # 테이블을 그릴 때 (work_name, batch_id) 쌍을 기준으로 정확히 열을 나눠야 해
    # 동일한 작업명 내에서 batch_id가 생성된 시간 순서대로 (1), (2), (3) 번호를 붙여줘
    filtered_analysis_results = all_analysis_results.filter(
        work_name__isnull=False
    ).exclude(
        Q(work_name='') | Q(work_name__isnull=True)
    ).order_by('work_name', 'created_at')
    
    # (work_name, batch_id) 쌍으로 그룹화하고 생성 순서대로 정렬
    distinct_combinations = []
    header_info = []
    work_name_groups = {}
    
    # work_name별로 그룹화하면서 생성 시간 순서대로 batch_id 정렬
    for result in filtered_analysis_results:
        work_name = result.work_name or "제목 없는 분석"
        batch_id = result.batch_id or ""
        combination_key = f"{work_name}_{batch_id}" if batch_id else work_name
        
        if work_name not in work_name_groups:
            work_name_groups[work_name] = []
        
        # 중복 방지
        if not any(item['batch_id'] == batch_id for item in work_name_groups[work_name]):
            work_name_groups[work_name].append({
                'combination': combination_key,
                'batch_id': batch_id,
                'created_at': result.created_at
            })
    
    # 헤더 정보 생성 (work_name별로 정렬하고 생성 시간 순서대로 번호 부여)
    for work_name, group in sorted(work_name_groups.items(), key=lambda x: x[0]):
        # 생성 시간 순서대로 정렬
        group_sorted = sorted(group, key=lambda x: x['created_at'])
        
        for idx, item in enumerate(group_sorted, 1):
            if len(group_sorted) > 1:
                display_name = f"{work_name[:8]}... ({idx})"
            else:
                display_name = work_name if len(work_name) <= 10 else f"{work_name[:10]}..."
            
            combination_key = item['combination']
            distinct_combinations.append(combination_key)
            
            header_info.append({
                'combination': combination_key,
                'work_name': work_name,
                'batch_id': item['batch_id'],
                'display_name': display_name,
                'order': idx
            })
    
    print(f"DEBUG: 추출된 조합들: {distinct_combinations}")
    print(f"DEBUG: 헤더 정보: {header_info}")
    
    # 해당 활동의 모든 답안 가져오기 (성능을 위해 딕셔너리로 가공)
    answers_qs = Answer.objects.filter(student__in=target_students, question=question).select_related('student')
    answer_map = {a.student_id: a for a in answers_qs}
    
    analysis_results = filtered_analysis_results.filter(answer__in=answers_qs)
    
    # [좌표 매칭 기반 렌더링] 헤더(Column)와 데이터(Row) 시스템 구축
    # 헤더(Column): (work_name, batch_id)의 고유 조합 리스트를 생성 시간 순으로 추출해 header_list로 정의
    header_list = AnalysisResult.objects.filter(
        answer__question__activity=activity,
        work_name__isnull=False
    ).exclude(
        Q(work_name='') | Q(work_name__isnull=True)
    ).values('work_name', 'batch_id').distinct().order_by('created_at')
    
    # None/빈값 방어: work_name이 None이거나 빈 문자열인 경우, '제목 없는 분석'으로 보정
    header_combinations = []
    for combo in header_list:
        work_name = combo['work_name'] or "제목 없는 분석"
        batch_id = combo['batch_id'] or ""
        combination_key = f"{work_name}_{batch_id}" if batch_id else work_name
        header_combinations.append({
            'work_name': work_name,
            'batch_id': batch_id,
            'combination_key': combination_key
        })
    
    print(f"[헤더] 추출된 조합들: {[h['combination_key'] for h in header_combinations]}")
    
    # 데이터(Row): 각 학생의 행을 구성할 때, 해당 학생의 모든 결과를 {batch_id: result_obj} 형태의 딕셔너리로 먼저 가공
    student_data_dict = {}
    for result in analysis_results:
        answer_id = result.answer_id
        if answer_id not in student_data_dict:
            student_data_dict[answer_id] = {}
        
        work_name = result.work_name or "제목 없는 분석"
        result_key = f"{work_name}_{result.batch_id}" if result.batch_id else work_name
        
        # {batch_id: result_obj} 형태의 딕셔너리로 가공
        student_data_dict[answer_id][result_key] = {
            'id': result.id,
            'content': result.result_content,
            'created_at': result.created_at,
            'created_at_formatted': timezone.localtime(result.created_at).strftime('%m-%d %H:%M'),
            'work_name': result.work_name,
            'batch_id': result.batch_id
        }
    
    # 슬롯 채우기: header_list를 기준으로 루프를 돌며, 학생의 딕셔너리에 해당 batch_id가 있으면 데이터 삽입, 없으면 None(빈칸)을 넣어 analysis_slots 완성
    student_data_list = []
    
    for student in target_students:
        answer = answer_map.get(student.id)
        answer_id = answer.id if answer else None
        
        # 상태 판별 로직
        if not answer:
            status = "미응시"
        elif not answer.submitted_at:
            status = "응시 중"
        elif not answer.content.strip():
            status = "백지 제출"
        else:
            status = "제출 완료"
            
        analysis_slots = []
        for header in header_info:
            combination_key = header['combination']
            
            # 학생의 딕셔너리에 해당 batch_id가 있는지 확인
            if answer_id and combination_key in student_data_dict.get(answer_id, {}):
                # 데이터 있음 -> 삽입 성공
                result_obj = student_data_dict[answer_id][combination_key]
                analysis_slots.append(result_obj)
            else:
                # 데이터 없음 -> 빈칸 처리
                analysis_slots.append(None)
        
        student_data_list.append({
            'student': student,
            'answer': answer, # 답안이 없으면 None
            'status': status, # [추가] 상태 정보
            'analysis_slots': analysis_slots  # header_list 순서대로 좌표 매칭 완료
        })
    
    # 학생 정렬 (학년/반/번호 순)
    
    # 학생 정렬 (학년/반/번호 순)
    student_data_list.sort(key=lambda x: (x['student'].grade, x['student'].class_no, x['student'].number))

    context = {
        'activity': activity,
        'question': question,
        'student_data_list': student_data_list,
        'filter_data': filter_data,
        'selected_targets': selected_targets,
        'current_q': name_query,
        'unique_combinations': [h['combination_key'] for h in header_combinations],  # 테이블 헤더용 (조합)
        'header_info': header_info,  # 미리 계산된 헤더 정보
    }
    return render(request, 'activities/activity_analysis.html', context)

# [1-1] 배치 판별 API (수석 엔지니어 확정 설계도)
@csrf_exempt
@login_required
def get_or_create_batch(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            work_name = body.get('work_name', '')
            student_ids = body.get('student_ids', [])
            activity_id = body.get('activity_id')
            
            print(f"[배치 판별] work_name: {work_name}, activity_id: {activity_id}")
            
            # 활동 정보 가져오기
            activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
            
            # 1) 현재 work_name과 activity_id로 저장된 모든 기존 AnalysisResult 학생 ID 세트(A)를 가져와
            existing_results = AnalysisResult.objects.filter(
                work_name=work_name,
                answer__question__activity=activity
            ).select_related('answer')
            
            # 기존 학생 ID 세트(A) - 반드시 str()로 형변환하여 비교
            existing_student_ids = set(str(result.answer_id) for result in existing_results)
            
            # 2) 이번에 분석할 학생 ID 세트(B)를 가져와 (반드시 str()로 형변환)
            current_student_ids = set(str(student_id) for student_id in student_ids)
            
            # 3) [교집합 확인]: not (A & B) 인지 확인
            intersection = existing_student_ids & current_student_ids
            has_intersection = len(intersection) > 0
            
            print(f"[세트 분석] 기존(A): {sorted(existing_student_ids)}, 요청(B): {sorted(current_student_ids)}")
            print(f"[교집합] A ∩ B = {sorted(intersection)}, 크기: {len(intersection)}")
            
            if not has_intersection:
                # 3-1) 교집합이 비어있다면: 기존의 가장 최신 batch_id를 반환해
                latest_result = existing_results.order_by('-created_at').first()
                if latest_result and latest_result.batch_id:
                    batch_id = latest_result.batch_id
                    print(f"[결정] 교집합 없음 -> 기존 최신 batch_id '{batch_id}' 재사용")
                else:
                    # 첫 분석인 경우
                    now = timezone.localtime(timezone.now())
                    batch_suffix = now.strftime('%m%d_%H%M')
                    batch_id = f"{work_name}_{batch_suffix}" if work_name else f"분석_{batch_suffix}"
                    print(f"[결정] 첫 분석 -> 새 batch_id '{batch_id}' 생성")
            else:
                # 4) [분리 확인]: 교집합이 있다면 무조건 새로운 batch_id 생성
                now = timezone.localtime(timezone.now())
                batch_suffix = now.strftime('%m%d_%H%M')
                batch_id = f"{work_name}_{batch_suffix}" if work_name else f"분석_{batch_suffix}"
                print(f"[결정] 교집합 존재 -> 새 batch_id '{batch_id}' 생성")
            
            return JsonResponse({
                'status': 'success',
                'batch_id': batch_id,
                'has_intersection': has_intersection,
                'intersection_count': len(intersection),
                'existing_count': len(existing_student_ids),
                'current_count': len(current_student_ids)
            })
            
        except Exception as e:
            print(f"[오류] 배치 판별 실패: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)})

# [2] 종합 분석 (모든 평가 매트릭스)
@login_required
@teacher_required
def integrated_analysis(request):
    # 1. 필터링을 위한 전체 학생 가져오기 (기존 로직 재사용)
    all_students = get_accessible_students(request.user)
    
    # --- 필터 데이터 생성 (기존과 동일) ---
    temp_dict = {}
    for s in all_students:
        g = s.grade
        c = s.class_no
        if g not in temp_dict: temp_dict[g] = []
        if c not in temp_dict[g]: temp_dict[g].append(c)
    
    filter_data = []
    for g in sorted(temp_dict.keys()):
        filter_data.append({'grade': g, 'classes': sorted(list(set(temp_dict[g])))})
    
    # 2. 검색 조건 처리
    selected_targets = request.GET.getlist('target') 
    name_query = request.GET.get('q', '')

    # 초기값 설정 (1학년 1반)
    if not selected_targets and not name_query and filter_data:
        g = filter_data[0]['grade']
        c = filter_data[0]['classes'][0]
        selected_targets = [f"{g}_{c}"]

    # 필터링 적용
    target_students = all_students
    if selected_targets:
        q_objects = Q()
        for t in selected_targets:
            if '_' in t:
                g, c = t.split('_')
                q_objects |= Q(grade=g, class_no=c)
        target_students = target_students.filter(q_objects)
    if name_query:
        target_students = target_students.filter(name__contains=name_query)

    # ----------------------------------------------------
    # ★ [핵심] 가로축(열) 만들기: 선생님이 만든 모든 평가 가져오기
    activities = Activity.objects.filter(teacher=request.user).order_by('created_at')
    
    # ★ [핵심] 데이터 매트릭스 만들기 (학생 x 평가)
    analysis_table = []
    
    for student in target_students:
        row_data = {
            'student': student,
            'answers': [] # 평가 순서대로 답안을 채워 넣음
        }
        
        for act in activities:
            # 해당 평가의 첫 번째 질문에 대한 이 학생의 답안 찾기
            question = act.questions.first()
            if question:
                ans = Answer.objects.filter(student=student, question=question).first()
                if ans:
                    # 내용이 있으면 내용, 없으면 결시 사유 등 표시
                    row_data['answers'].append(ans.content if ans.content.strip() else f"({ans.get_absence_type_display()})")
                else:
                    row_data['answers'].append("") # 미응시 (빈칸)
            else:
                row_data['answers'].append("-") # 질문 없음
                
        analysis_table.append(row_data)

    context = {
        'filter_data': filter_data,
        'selected_targets': selected_targets,
        'current_q': name_query,
        'activities': activities,   # 헤더(가로축)
        'analysis_table': analysis_table # 본문(데이터)
    }
    return render(request, 'activities/integrated_analysis.html', context)

# [3] 분석 작업 실행 페이지 (프롬프트 입력 환경)
@login_required
@teacher_required
def activity_analysis_work(request, activity_id):
    # [함수 시작] 변수 초기화 (기본값 설정)
    selected_student_ids = []
    work_name = ""
    answer_list = []
    
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    question = activity.questions.first()
    
    # [분석 데이터 조회] 해당 활동의 가장 최신 AnalysisResult에서 work_name 가져오기 (GET 진입 시 자동 완성용)
    latest_result = AnalysisResult.objects.filter(
        answer__question__activity=activity,
        work_name__isnull=False
    ).exclude(work_name='').order_by('-created_at').first()
    work_name = latest_result.work_name if latest_result else ""
    print(f"DEBUG: 저장된 마지막 작업명 찾음 -> {work_name}")
    
    # 질문이 존재할 때만 답안을 찾음
    if question:
        # 활동의 대상 학생들 중에서만 content가 비어있지 않은(공백 제외) 답안만 가져옵니다.
        target_student_ids = activity.target_students.values_list('id', flat=True)
        answers = Answer.objects.filter(
            question=question,
            student_id__in=target_student_ids
        ).exclude(content='').select_related('student') # 실제 내용이 있는 것만!

        for a in answers:
            if a.content and a.content.strip():
                answer_list.append({
                    'id': a.id,
                    'student_id': a.student.id,  # 명확한 학생 ID 필드 추가
                    'name': a.student.name,
                    'info': f"{a.student.grade}-{a.student.class_no}-{a.student.number}"
                })

    # 만약 answer_list가 비어있다면 명시적으로 '[]' 문자열을 만듦
    answer_list_json = json.dumps(answer_list) if answer_list else "[]"

    print("DEBUG: AI 분석 설정 페이지 진입 성공")
    
    # [POST 요청 시] 화면에서 넘어온 work_name과 target_students 리스트를 업데이트
    if request.method == 'POST':
        selected_student_ids = request.POST.getlist('target_students')
        work_name = request.POST.get('work_name', work_name)  # POST 값이 있으면 업데이트, 없으면 기존 값 유지
        print(f"DEBUG: 현재 선택된 학생들 -> {selected_student_ids}")
        print(f"DEBUG: 현재 작업명 -> {work_name}")
    
    # [마무리] 모든 변수(work_name, selected_student_ids 등)를 context에 담아 템플릿으로 전달

    context = {
        'activity': activity,
        'question': question,
        'submit_count': len(answer_list),
        'answer_list_json': answer_list_json, # 이제 무조건 '[]' 라도 나감
        'prompt_templates': PromptTemplate.objects.all(),
        'length_options': PromptLengthOption.objects.all(),
        'student_tree': get_student_tree(request.user),
        'current_targets': selected_student_ids, # 템플릿에 전달
        'work_name': work_name, # 작업명 템플릿에 전달
    }
    return render(request, 'activities/activity_analysis_work.html', context)

# [4] AI API 호출 및 DB 저장 (멀티 모델 지원 핵심 로직)
@csrf_exempt
@login_required
def api_process_db_row(request):
    if request.method == 'POST':
        try:
            print("DEBUG: 분석 요청 수신 시작")
            print(f"DEBUG: 수신 데이터 -> {request.body}")
            body = json.loads(request.body)
            answer_id = body.get('answer_id')
            prompt_system = body.get('prompt_system')
            temperature = float(body.get('temperature', 0.7))
            work_name = body.get('work_name', '')
            batch_id = body.get('batch_id', '')
            print(f"DEBUG: 분석 요청 수신 -> answer_id: {answer_id}, work_name: {work_name}, batch_id: {batch_id}")
            
            # 분석 모델은 설정값/요청값을 사용하지 않고 서버에서 고정합니다.
            ai_model = FORCED_AI_ANALYSIS_MODEL

            # 2. 답안 및 활동 정보 가져오기
            answer = Answer.objects.get(id=answer_id)
            activity = answer.question.activity # 역참조로 활동 정보 획득
            student = answer.student
            
            # 3. batch_id 처리 - 프론트엔드에서 결정한 값 그대로 사용
            print(f"DEBUG: 프론트엔드에서 받은 Batch ID: {batch_id}")
            print(f"DEBUG: 단일 학생(answer_id: {answer.id}) 분석 시작")
            
            # [방어 로직] 답안이 비어있으면 AI 호출 없이 리턴
            if not answer.content or not answer.content.strip():
                return JsonResponse({
                    'status': 'skipped', 
                    'message': '내용이 없는 답안은 분석하지 않습니다.'
                })

            # 3. 프롬프트에 활동 상세 정보 통합
            # AI에게 "문제와 조건"을 먼저 알려주어 분석 정확도를 높입니다.
            activity_context = f"""
[활동 정보 및 컨텍스트]
- 활동명: {activity.section}
- 평가 주제: {activity.title}
- 평가 문항: {activity.question}
- 참고 자료: {activity.reference_material}
- 작성 조건: {activity.conditions}
- 권장 분량: {activity.char_limit}자 이내
"""
            student_info = f"[대상 학생: {student.name}({student.grade}-{student.class_no}-{student.number})]"
            
            # 최종 지시사항 조립 (활동 정보 + 학생 답안 + 교사 지시사항)
            final_prompt = f"{activity_context}\n{student_info}\n[학생 답안 내용]\n{answer.content}\n\n[AI 지시사항]\n{prompt_system}"
            
            result_text = ""

            # ---------------------------------------------------------
            # [엔진 분기] AI 모델별 API 호출 분기 처리 Gemini / GPT / Claude
            # ---------------------------------------------------------
            
            # ---------------------------------------------------------
            # [분기 1] Google Gemini 엔진 (gemini- 로 시작할 때)
            # ---------------------------------------------------------
            if ai_model.startswith('gemini'):
                config = SystemConfig.objects.get(key_name='GOOGLE_API_KEY')
                api_key = config.value.strip()
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{ai_model}:generateContent?key={api_key}"
                
                payload = {
                    "contents": [{"parts": [{"text": final_prompt}]}],
                    "generationConfig": {"temperature": temperature}
                }
                response = requests.post(url, json=payload, timeout=60)
                
                if response.status_code == 429:
                    return JsonResponse({'status': 'error', 'message': 'Gemini 서버 과부하(429).'}, status=429)
                
                res_data = response.json()
                if "candidates" in res_data:
                    result_text = res_data["candidates"][0]["content"]["parts"][0]["text"]

            # ---------------------------------------------------------
            # [분기 2] OpenAI GPT 엔진 (gpt- 로 시작할 때)
            # ---------------------------------------------------------
            elif ai_model.startswith('gpt'):
                config = SystemConfig.objects.get(key_name='OPENAI_API_KEY')
                api_key = config.value.strip()
                url = "https://api.openai.com/v1/chat/completions"
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": ai_model,
                    "messages": [
                        {"role": "system", "content": "당신은 생활기록부 작성 및 학생 분석 전문가입니다."},
                        {"role": "user", "content": final_prompt}
                    ],
                    "temperature": temperature
                }
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 429:
                    return JsonResponse({'status': 'error', 'message': 'GPT 서버 과부하(429).'}, status=429)
                
                res_data = response.json()
                if "choices" in res_data:
                    result_text = res_data["choices"][0]["message"]["content"]

            # ---------------------------------------------------------
            # [분기 3] Anthropic Claude 엔진 (claude- 로 시작할 때)
            # ---------------------------------------------------------
            elif ai_model.startswith('claude'):
                config = SystemConfig.objects.get(key_name='CLAUDE_API_KEY')
                api_key = config.value.strip()
                url = "https://api.anthropic.com/v1/messages"
                
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": ai_model,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": final_prompt}],
                    "temperature": temperature
                }
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                res_data = response.json()
                if "content" in res_data:
                    result_text = res_data["content"][0]["text"]

            # ---------------------------------------------------------
            # 4. 분석 결과 DB 저장 (다중 결과 지원)
            # ---------------------------------------------------------
            if result_text:
                try:
                    print(f"DEBUG: AnalysisResult 저장 시도 - answer_id: {answer.id}, work_name: {work_name}, batch_id: {batch_id}")
                    print(f"DEBUG: 저장할 데이터 - result_content 길이: {len(result_text)}, ai_model: {ai_model}")
                    
                    # AnalysisResult 모델에 단일 학생 결과 저장 (update_or_create 사용)
                    final_work_name = work_name if work_name else "제목 없는 분석"
                    created_result, created = AnalysisResult.objects.update_or_create(
                        answer_id=answer.id,  # 오직 이 answer_id에 대해서만
                        work_name=final_work_name,
                        batch_id=batch_id,
                        defaults={
                            'result_content': result_text,
                            'prompt_system': prompt_system,
                            'temperature': temperature,
                            'ai_model': ai_model,
                        }
                    )
                    
                    action = "생성" if created else "업데이트"
                    print(f"DEBUG: AnalysisResult {action} 성공 - result_id: {created_result.id}, work_name: '{created_result.work_name}'")
                    
                    # Answer 모델에도 최신 결과 업데이트 (호환성)
                    answer.ai_result = result_text
                    answer.ai_updated_at = timezone.now()
                    answer.save()
                    
                    print(f"DEBUG: 단일 학생(answer_id: {answer.id}) 처리 완료 - result_id: {created_result.id}")
                    return JsonResponse({'status': 'success', 'result': '저장 완료'})
                except Exception as e:
                    print(f"ERROR: AnalysisResult 저장 실패 - {str(e)}")
                    print(f"ERROR: 실패 상세 - answer_id: {answer.id}, work_name: {work_name}, batch_id: {batch_id}")
                    return JsonResponse({'status': 'error', 'message': f'데이터 저장 실패: {str(e)}'})
            else:
                print(f"DEBUG: AI 응답 없음 - answer_id: {answer.id}")
                return JsonResponse({'status': 'error', 'message': 'AI 응답이 없습니다.'})
            
        except SystemConfig.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': '관리자 페이지에서 API_KEY를 등록해주세요.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'fail'}, status=400)
