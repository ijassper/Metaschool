from django.db import migrations


PRESETS = [
    {
        "level": 4,
        "name": "요약 지침·간략한 명확형",
        "prompt_rules": (
            "부연 설명, 배경 설명과 긴 인과 묘사를 덜어내고 학생이 고쳐야 할 핵심 요점과 수정 지침을 직관적이고 간결하게 전달하세요. "
            "각 선택 구성 항목에서는 강점이나 문제와 핵심 근거를 한 문장 안팎으로 명시하고, 개선 방향은 추가하거나 수정할 내용을 바로 실행할 수 있는 지침으로 제시하세요. "
            "긴 예시문, 단계별 목록, 반복 설명과 불필요한 수식어를 사용하지 마세요. "
            "간략하게 쓰더라도 선택된 피드백 구성 항목을 누락하거나 답안 근거 없이 단정하지 마세요."
        ),
        "source_guide": (
            "간략한 명확형 1단계는 요약 지침형이다. 부연과 배경 설명을 줄이고 핵심 지적과 직관적인 수정 가이드를 제공한다. "
            "강점은 장점과 핵심 가치를 1~2문장으로 압축한다. 약점은 논리적 상충 지점과 원인을 군더더기 없이 짚는다. "
            "개선 방향은 보완해야 할 핵심 서술 요소를 바로 실행할 수 있는 지침으로 요약한다. 전체 호흡은 중립 단계보다 짧게 유지한다."
        ),
        "example_text": (
            "2번에서 학습에 영향이 없다고 기술한 부분은 1번의 문제의식 및 4번의 감축 계획과 논리적으로 상충한다. "
            "6~7시간의 기기 사용으로 발생한 집중력 저하와 공부 시간 부족을 솔직하게 기술하여 글의 일관성을 맞추어야 한다."
        ),
    },
    {
        "level": 5,
        "name": "최대 간략·초압축 핵심 지침형",
        "prompt_rules": (
            "맥락 설명, 부연과 수식어를 배제하고 평가 결과 및 수정해야 할 핵심 조치만 가장 짧고 명확하게 작성하세요. "
            "선택된 각 피드백 구성 항목은 핵심 문장 1개, 필요한 경우에만 최대 2개의 짧은 문장으로 제한하세요. "
            "강점은 잘된 핵심 요소 하나를 단정하고, 약점은 오류나 논리 결함 하나를 짚으며, 개선 방향은 구체적인 수정 행동 하나를 명시하세요. "
            "별도의 해석 없이 바로 실행할 수 있는 표현을 사용하되 무례한 명령, 근거 없는 평가와 선택 항목 누락은 피하세요."
        ),
        "source_guide": (
            "간략한 명확형 2단계는 최대 간략·초압축 핵심 디렉션형이다. 왜 그런지에 관한 배경 설명을 걷어내고 결론과 행동 지침만 전달한다. "
            "모든 선택 구성 요소를 핵심 문장 1~2줄로 구성한다. 강점은 잘된 요소 하나, 약점은 결함 지점 하나, 개선 방향은 수정 조치 하나로 압축한다. "
            "텍스트 분량을 최소화하지만 실제 답안 근거와 교육적으로 안전한 표현은 유지한다."
        ),
        "example_text": (
            "2번의 '학습 영향 없음' 서술은 1번의 집중력 저하 및 4번의 시간 감축과 모순된다. "
            "2번에 하루 6~7시간 사용으로 인한 공부 시간 부족과 집중력 저하를 직접 명시하여 수정할 것."
        ),
    },
]


def seed_concise_detail_presets(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    for preset in PRESETS:
        ToneStylePreset.objects.update_or_create(
            dimension="detail",
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


def remove_concise_detail_presets(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.filter(dimension="detail", level__in=[4, 5]).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0016_seed_detailed_tone_presets")]
    operations = [migrations.RunPython(seed_concise_detail_presets, remove_concise_detail_presets)]
