# AI 분석 및 프롬프트 (activity_analysis, api_process_db_row 등)

import json
import requests
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 커스텀 데코레이터 및 계정 모델 임포트
from accounts.decorators import teacher_required
from accounts.models import Student, SystemConfig, PromptTemplate, PromptLengthOption
from ..models import Activity, Question, Answer

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
        all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')

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

    # 6. 분석용 데이터 리스트 생성
    # (제출 현황과 달리, 여기서는 '답안 내용'이 중요합니다)
    analysis_list = []
    
    for student in target_students:
        answer = Answer.objects.filter(student=student, question=question).first()
        
        # 기본값 설정
        content = ""
        ans_q1 = ""
        ans_q2 = ""
        ans_q3 = ""
        submitted_at = ""
        ai_result = ""
        ai_updated_at = "" # 그리드 뷰에서 사용됨
        has_answer = False

        if answer:
            has_answer = True
            content = answer.content
            # [핵심] 분리된 개별 답변들을 변수에 담아줍니다.
            ans_q1 = answer.ans_q1
            ans_q2 = answer.ans_q2
            ans_q3 = answer.ans_q3
            submitted_at = answer.submitted_at
            ai_result = answer.ai_result
            ai_updated_at = answer.ai_updated_at
        
        analysis_list.append({
            'student': student,
            'has_answer': has_answer,
            'content': content,
            'ans_q1': ans_q1, # 템플릿의 {{ item.ans_q1 }}과 연결됨
            'ans_q2': ans_q2,
            'ans_q3': ans_q3,
            'submitted_at': submitted_at,
            'ai_result': ai_result,
            'ai_updated_at': ai_updated_at,
        })

    context = {
        'activity': activity,
        'question': question,
        'analysis_list': analysis_list,
        'filter_data': filter_data,
        'selected_targets': selected_targets,
        'current_q': name_query,
    }
    return render(request, 'activities/activity_analysis.html', context)

# [2] 종합 분석 (모든 평가 매트릭스)
@login_required
@teacher_required
def integrated_analysis(request):
    # 1. 필터링을 위한 전체 학생 가져오기 (기존 로직 재사용)
    all_students = Student.objects.filter(teacher=request.user).order_by('grade', 'class_no', 'number')
    
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
    activity = get_object_or_404(Activity, id=activity_id, teacher=request.user)
    question = activity.questions.first()
    
    answer_list = [] # 기본값은 빈 리스트
    
    # 질문이 존재할 때만 답안을 찾음
    if question:
        # content가 비어있지 않은(공백 제외) 답안만 가져옵니다.
        answers = Answer.objects.filter(
            question=question
        ).exclude(content='').select_related('student') # 실제 내용이 있는 것만!

        for a in answers:
            if a.content and a.content.strip():
                answer_list.append({
                    'id': a.id,
                    'name': a.student.name,
                    'info': f"{a.student.grade}-{a.student.class_no}-{a.student.number}"
                })

    # 만약 answer_list가 비어있다면 명시적으로 '[]' 문자열을 만듦
    answer_list_json = json.dumps(answer_list) if answer_list else "[]"

    context = {
        'activity': activity,
        'question': question,
        'submit_count': len(answer_list),
        'answer_list_json': answer_list_json, # 이제 무조건 '[]' 라도 나감
        'prompt_templates': PromptTemplate.objects.all(),
        'length_options': PromptLengthOption.objects.all(),
    }
    return render(request, 'activities/activity_analysis_work.html', context)

# [4] AI API 호출 및 DB 저장 (멀티 모델 지원 핵심 로직)
@csrf_exempt
@login_required
def api_process_db_row(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            answer_id = body.get('answer_id')
            prompt_system = body.get('prompt_system')
            temperature = float(body.get('temperature', 0.7))
            
            # 1. 설정 페이지에서 선택된 AI 모델 가져오기
            try:
                model_cfg = SystemConfig.objects.get(key_name='SELECTED_AI_MODEL')
                ai_model = model_cfg.value.strip()
            except SystemConfig.DoesNotExist:
                ai_model = 'gemini-2.0-flash' # 기본값

            # 2. 답안 및 활동 정보 가져오기
            answer = Answer.objects.get(id=answer_id)
            activity = answer.question.activity # 역참조로 활동 정보 획득
            student = answer.student
            
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
            # 4. 분석 결과 DB 저장 (공통 처리)
            # ---------------------------------------------------------
            if result_text:
                answer.ai_result = result_text
                answer.ai_updated_at = timezone.now()
                answer.save()
                return JsonResponse({'status': 'success', 'result': '저장 완료'})
            else:
                return JsonResponse({'status': 'error', 'message': f'AI 응답 실패: {response.text}'})
            
        except SystemConfig.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': '관리자 페이지에서 API_KEY를 등록해주세요.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'fail'}, status=400)