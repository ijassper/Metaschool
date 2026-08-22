from django.db import migrations


PRESETS = [
    {
        "level": 4,
        "name": "완곡한 제안·성장 코칭형",
        "prompt_rules": (
            "학생의 생각과 노력을 먼저 긍정적으로 수용한 뒤 보완할 지점을 부드럽게 덧붙이는 '수용 후 보완' 화법을 사용하세요. "
            "'틀렸다, 모순이다'처럼 직접 규정하지 말고 '독자 입장에서는 앞뒤 연결이 조금 어색하게 느껴질 수 있다, 조금 더 설명이 필요해 보인다'처럼 독자와 맥락의 관점에서 문제를 제기하세요. "
            "개선안은 명령이 아니라 '이렇게 보완하면 설득력이 한층 높아질 수 있다, 구체적으로 풀어내면 더 돋보일 것이다'처럼 성장 가능성을 보여주는 권유형으로 작성하세요. "
            "칭찬은 작성자의 노력, 긍정적인 발상과 세부적인 고민의 흔적을 답안 근거와 함께 따뜻하게 조명하세요. "
            "완곡하게 표현하더라도 핵심 개선 지점과 그 근거를 생략하거나 답안에 없는 감정과 경험을 만들어내지 마세요."
        ),
        "source_guide": (
            "우회적 1단계는 완곡한 제안과 성장 관점의 부드러운 코칭 화법이다. 작성자의 생각을 먼저 수용하고 보완점을 제시한다. "
            "문제를 학생의 결함으로 규정하지 않고 독자가 느낄 수 있는 연결의 어색함이나 추가 설명의 필요성으로 전환한다. "
            "지시보다 자발적인 수정을 권장하며, 보완 후 글의 설득력과 장점이 어떻게 살아날지를 보여준다. "
            "칭찬은 노력과 발상, 고민의 흔적을 구체적인 답안 근거로 설명한다."
        ),
        "example_text": (
            "2번 항목에서 학습에 영향이 없다고 작성한 부분은 조금 아쉬움이 남는다. "
            "1번에서 집중력에 미치는 영향을 깨닫고 4번에서 사용 시간을 줄이겠다고 다짐한 흐름과 비교하면, 2번의 설명은 자신의 일상과 조금 거리를 둔 듯한 인상을 줄 수 있다. "
            "스마트폰을 사용하며 느낀 피로나 자율 학습 시간의 부족을 조금 더 솔직하게 연결해 본다면, 4번의 실천 계획이 필요한 이유와 글의 설득력이 한층 더 돋보일 것이다."
        ),
    },
    {
        "level": 5,
        "name": "최대 우회·열린 질문 코칭형",
        "prompt_rules": (
            "문제나 결함을 직접 규정하는 서술을 피하고, 학생이 글을 다시 읽으며 생각의 틈을 스스로 발견하도록 열린 질문과 성찰 중심의 코칭을 사용하세요. "
            "'수정해라, 아쉽다' 대신 '두 내용 사이에는 어떤 연결고리가 있을까, 그때 실제로 어떤 변화가 있었을까, 독자는 이 부분을 어떻게 이해할까'처럼 정답을 강요하지 않는 질문을 제시하세요. "
            "보완점을 고쳐야 할 결함이 아니라 생각을 더 발전시킬 탐구 지점으로 재해석하고, 학생이 자기 경험과 판단을 점검해 답을 문장에 담도록 안내하세요. "
            "칭찬에도 학생이 계획의 의미와 가능성을 스스로 발견할 수 있는 성찰 질문을 자연스럽게 결합하세요. "
            "질문은 답안에서 실제로 확인되는 내용에 근거해야 하며, 우회적인 표현 때문에 핵심 성찰 지점이 누락되거나 모호해지지 않게 하세요."
        ),
        "source_guide": (
            "우회적 2단계는 문제 지적을 배제하고 메타인지와 자기 점검을 자극하는 최대 우회 화법이다. "
            "피드백 제공자가 정답이나 결함을 규정하지 않고 열린 질문으로 학생의 자기 발견을 촉진한다. "
            "독자의 궁금증과 글 안의 서로 다른 내용을 질문으로 연결하고, 학생이 변화의 과정과 이유를 스스로 탐색하도록 한다. "
            "개선 과제는 생각을 깊게 발전시킬 탐구 지점으로 제시하며 질문의 근거는 반드시 실제 답안에서 가져온다."
        ),
        "example_text": (
            "2번 항목에서 학습에 영향이 없다고 작성한 부분은 스스로에게 한 번 더 질문을 던져볼 만한 지점이다. "
            "1번에서 집중력과 수면에 미치는 영향을 깨닫고 4번에서 사용 시간을 줄이겠다고 다짐했는데, 2번의 답변과 4번의 결심 사이에는 어떤 마음의 변화나 연결고리가 있었을까? "
            "하루 6~7시간을 사용할 때 느꼈던 집중의 변화와 시간의 흐름을 떠올리고, 그 경험이 실천 계획으로 어떻게 이어졌는지 차분히 적어보는 것은 어떨까? "
            "그 과정을 문장으로 엮으면 글쓴이만의 성찰이 더 깊게 드러날 것이다."
        ),
    },
]


def seed_indirect_directness_presets(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    for preset in PRESETS:
        ToneStylePreset.objects.update_or_create(
            dimension="directness",
            level=preset["level"],
            defaults={
                "name": preset["name"],
                "prompt_rules": preset["prompt_rules"],
                "source_guide": preset["source_guide"],
                "example_text": preset["example_text"],
                "is_active": True,
                "version": 1,
            },
        )


def remove_indirect_directness_presets(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.filter(dimension="directness", level__in=[4, 5]).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0014_refine_neutral_directness_tone_preset")]
    operations = [
        migrations.RunPython(
            seed_indirect_directness_presets,
            remove_indirect_directness_presets,
        )
    ]
