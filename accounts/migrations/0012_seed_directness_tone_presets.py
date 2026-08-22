from django.db import migrations


PRESETS = [
    {
        "level": 1,
        "name": "최대 직설·완충 표현 배제",
        "prompt_rules": (
            "완충 표현과 감성적 수식어를 배제하고 문제의 원인, 논리적 오류와 수정 사항을 정면으로 명시하세요. "
            "'조금 아쉽다, 살짝, 더 좋을 것 같다, 어떨까' 같은 쿠션어를 사용하지 말고, 근거가 분명할 때 "
            "'오류다, 모순이다, 틀렸다, 부족하다'처럼 상태를 정확히 규정하세요. "
            "칭찬도 미사여구 없이 어떤 요소가 왜 잘되었는지 객관적 사실로 짧게 설명하세요. "
            "개선안은 질문형 제안 대신 '수정해야 한다, 삭제하고 다시 작성해야 한다'처럼 즉시 실행할 행동을 직접 지시하세요. "
            "학생의 인격이나 능력을 공격하지 말고 오직 답안의 내용과 수정 가능한 행동만 단호하게 평가하세요."
        ),
        "source_guide": (
            "단도직입적 2단계로, 수식어와 완충 표현을 완전히 걷어낸 최대 직설 화법이다. "
            "문제점의 원인과 결과를 1:1로 연결해 설명하고 논리적 오류를 가감 없이 규정한다. "
            "칭찬은 감성적 반응 대신 잘 수행된 요소와 근거를 객관적으로 명시한다. "
            "약점은 모순·오류·부족함을 직접 밝히고, 개선 방향은 명령형 또는 단언형 액션 아이템으로 제시한다. "
            "직설성은 학생을 모욕하거나 낙인찍기 위한 것이 아니며 답안의 내용, 논리와 수정 행동에만 적용한다."
        ),
        "example_text": (
            "2번 항목에서 '스마트폰 사용이 나의 학습에 딱히 영향을 끼치지 않는다'고 작성한 것은 명백한 논리적 모순이다. "
            "하루 6~7시간을 미디어와 게임에 사용하면서 학업에 영향이 없다는 서술은 1번의 집중력 저하 문제와 4번의 감축 계획과 앞뒤가 맞지 않는다. "
            "2번 항목을 즉시 수정해야 한다. 과다 사용으로 발생한 집중력 저하와 시간 낭비를 사실대로 기술해야 전체 글의 논리가 성립된다."
        ),
    },
    {
        "level": 2,
        "name": "명확한 직접성·최소 안내형 완충",
        "prompt_rules": (
            "문제점을 에둘러 포장하지 말고 핵심 결함을 객관적이고 정제된 표현으로 바로 지적하세요. "
            "'틀렸다, 모순이다'처럼 날카로운 단정보다는 '논리적으로 상충된다, 보완이 필요하다, 일관성이 부족하다'를 사용하세요. "
            "감성적인 공감이나 불필요한 쿠션어 없이 왜 수정해야 하는지 원인과 결과를 명료하게 설명하세요. "
            "칭찬은 잘 수행한 요소의 실용성과 근거를 또렷하게 평가하고, 개선안은 질문형을 피한 채 변경 기준과 행동을 직접 안내하세요. "
            "학생의 인격이 아니라 답안의 내용과 수정 가능한 행동만 평가하세요."
        ),
        "source_guide": (
            "단도직입적 1단계로, 오류를 직접 짚되 공격적인 인상을 줄이지 않도록 최소한의 교수적 완충을 사용하는 화법이다. "
            "정제된 직접성, 명확한 인과 설명, 구체적인 대안 제시가 핵심이다. "
            "칭찬은 감정적 리액션을 절제하고 실용적 강점을 분명히 평가한다. "
            "약점에는 보완 필요성과 내용의 상충 관계를 명시하고, 개선 방향에는 일관성을 확보하기 위한 구체적 수정 기준을 제시한다."
        ),
        "example_text": (
            "2번 항목에서 '스마트폰 사용이 나의 학습에 딱히 영향을 끼치지 않는다'고 서술한 부분은 보완이 필요하다. "
            "하루 6~7시간을 오락 목적으로 사용하면서 학습에 영향이 없다고 기술한 것은 1번의 문제의식과 4번의 감축 계획과 내용상 상충된다. "
            "스마트폰 사용이 자율 학습 시간과 집중도에 미친 부정적인 영향을 솔직하게 서술하여 글의 논리적 일관성을 맞추어야 한다."
        ),
    },
]


def seed_directness_presets(apps, schema_editor):
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


def remove_directness_presets(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.filter(dimension="directness", level__in=[1, 2]).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0011_seed_formality_tone_presets")]
    operations = [migrations.RunPython(seed_directness_presets, remove_directness_presets)]
