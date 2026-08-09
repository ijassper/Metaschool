from django.db import migrations, models


CATEGORY_GUIDES = {
    "ESSAY": "논술 활동의 논지, 근거, 구성, 일관성과 문장 표현을 중심으로 판단하세요.",
    "CLUB": "동아리 활동의 참여 과정, 협업, 역할 수행, 탐구와 성찰을 중심으로 판단하세요.",
    "CAREER": "진로 활동의 자기이해, 탐색 과정, 계획의 구체성과 성찰을 중심으로 판단하세요.",
    "CREATIVE": "자율 활동의 자율성, 공동체성, 책임, 참여와 실천을 중심으로 판단하세요.",
}

TASK_PROMPTS = {
    "grading": (
        "평가 문항과 작성 조건을 먼저 확인하고 학생 답안에서 직접 확인되는 근거만 사용해 채점·분석하세요. "
        "잘한 점과 보완할 점을 구분하고, 추측하거나 낙인찍지 말며 다음 학습에 활용할 수 있는 구체적인 판단을 제공하세요."
    ),
    "rewrite": (
        "학생의 원래 생각과 목소리를 보존하면서 고쳐쓰기 활동을 설계하세요. 한 번에 모두 대신 써주지 말고, "
        "수정할 부분의 이유와 적용 가능한 예시, 학생이 직접 다시 쓸 수 있는 단계별 문항을 제공하세요."
    ),
    "relay": (
        "학생 답안의 핵심 생각과 분위기를 출발점으로 릴레이쓰기 활동을 설계하세요. 다음 작성자가 자연스럽게 "
        "이어갈 단서와 선택지를 주고, 원문을 존중하면서도 새로운 관점과 상상력을 확장하도록 안내하세요."
    ),
}

FEEDBACK_PROMPT = """### 피드백의 정의
- 피드백은 한국의 초등학교, 중학교 또는 고등학교에서 교사가 학생이 작성한 글에 제공하는 서술형 평가이며, 교사가 자기 학생에게 보내는 일상적인 편지글과 가장 유사합니다.
- 가장 중요한 원칙은 개별 학생이 글쓰기에 흥미를 갖고 이후 글쓰기 활동에 참여할 용기와 격려를 얻도록 하는 것입니다.

### 피드백의 형식
- 학생 답안을 상세히 분석하고, 학생이 다음 기회에 장점을 살리고 단점을 보완하도록 동기를 주는 한글 피드백을 작성하세요.
- 구성 항목은 인사말, 답안 요약, 내용에 대한 공감과 칭찬, 강점, 약점, 개선 방향, 지속 학습에 대한 격려, 마지막 인사말입니다. 교사가 선택한 항목만 취사선택해 반영하세요.
- 처음은 한국 교사가 일상에서 자기 학생을 부르듯 친근한 인사말로 시작하세요.
- 답안 요약은 글 전체를 온전히 읽었다는 인상을 주되 과도하지 않게 1~2문장으로 작성하세요.
- 공감과 칭찬에는 학생의 경험·감정에 대한 공감과 솔직하게 표현한 용기에 대한 칭찬을 담으세요.
- 강점은 흐름, 흥미성, 일관성, 응집성, 어휘 사용 등에서 가장 우수한 영역을 답안의 구체적인 근거와 함께 언급하세요.
- 약점은 가장 아쉬운 한두 영역만 신중하게 다루고, 학생이 글쓰기에 대한 용기와 동기를 잃지 않도록 다정하고 세심한 말투를 유지하세요.
- 개선 방향은 언급한 약점과 연결하여 어느 부분을 어떻게 고쳐 쓰면 좋은지 구체적으로 알려주세요.
- 지속 학습에 대한 격려에는 다음 글쓰기 활동에도 힘을 내도록 격려하는 내용을 담으세요.
- 마지막은 한국 교사가 일상에서 자기 학생에게 하듯 친근한 작별 인사로 마무리하세요.
- 높임말과 반말의 정도는 교사가 선택한 형식성에 맞추되 ‘귀하’, ‘학생님’처럼 교사가 학생에게 평소 사용하지 않을 호칭은 절대 사용하지 마세요.
- 일상적인 어휘와 다정하고 친근한 구어체로 통일하고, 선택된 형식성에 맞춰 ‘~했다.’, ‘~한다.’, ‘~이다.’, ‘~하렴.’, ‘~하네.’ 등의 자연스러운 종결 표현을 사용하세요."""


def create_multidimensional_personas(apps, schema_editor):
    Persona = apps.get_model("accounts", "Persona")
    category_labels = {"ESSAY": "논술", "CLUB": "동아리", "CAREER": "진로", "CREATIVE": "자율"}
    task_labels = {"grading": "채점/분석", "feedback": "피드백 제공", "rewrite": "고쳐쓰기", "relay": "릴레이쓰기"}

    for category, category_label in category_labels.items():
        for task_type, task_label in task_labels.items():
            task_prompt = FEEDBACK_PROMPT if task_type == "feedback" else TASK_PROMPTS[task_type]
            Persona.objects.update_or_create(
                creator=None,
                category_context=category,
                task_type=task_type,
                defaults={
                    "name": f"{category_label} {task_label} 교사",
                    "description": f"{category_label} 맥락에 최적화된 {task_label} 시스템 페르소나",
                    "system_prompt": f"{CATEGORY_GUIDES[category]}\n\n{task_prompt}",
                    "tone_default": "친절한" if task_type == "feedback" else "신뢰있는",
                    "is_default": True,
                },
            )


def remove_multidimensional_personas(apps, schema_editor):
    Persona = apps.get_model("accounts", "Persona")
    Persona.objects.filter(
        creator=None,
        category_context__in=CATEGORY_GUIDES.keys(),
        task_type__in=("grading", "feedback", "rewrite", "relay"),
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_persona")]

    operations = [
        migrations.AddField(
            model_name="persona",
            name="category_context",
            field=models.CharField(blank=True, choices=[("ESSAY", "논술"), ("CLUB", "동아리"), ("CAREER", "진로"), ("CREATIVE", "자율")], default="", max_length=20, verbose_name="활동 맥락"),
        ),
        migrations.AddField(
            model_name="persona",
            name="is_default",
            field=models.BooleanField(default=False, verbose_name="시스템 기본 제공"),
        ),
        migrations.AddField(
            model_name="persona",
            name="task_type",
            field=models.CharField(blank=True, choices=[("grading", "채점/분석"), ("feedback", "피드백 제공"), ("rewrite", "고쳐쓰기"), ("relay", "릴레이쓰기")], default="", max_length=20, verbose_name="작업 유형"),
        ),
        migrations.AddIndex(
            model_name="persona",
            index=models.Index(fields=["category_context", "task_type", "is_default"], name="persona_match_idx"),
        ),
        migrations.RunPython(create_multidimensional_personas, remove_multidimensional_personas),
    ]
