from django.db import migrations


PRESET = {
    "level": 3,
    "name": "균형 잡힌 진단·객관적 건설형",
    "prompt_rules": (
        "직설적 단정과 과도한 완곡 표현 사이의 균형을 유지하세요. "
        "먼저 답안에서 확인되는 사실과 강점을 객관적으로 설명한 뒤, 보완할 부분과 그 이유를 근거 중심으로 진단하세요. "
        "문제점을 숨기거나 과장하지 말고 '보완이 필요하다, 연결이 다소 약하다, 근거를 더 분명히 해야 한다'처럼 "
        "정확하지만 공격적이지 않은 표현을 사용하세요. "
        "개선 방향은 학생이 바로 실행할 수 있도록 구체적으로 제안하되 강압적인 명령이나 지나친 질문형 완충은 피하세요. "
        "칭찬, 진단, 개선안을 균형 있게 배치하고 학생의 인격이 아닌 답안의 내용과 표현만 평가하세요."
    ),
    "source_guide": (
        "솔직성 축의 중립 기준점이다. 문제를 감추지 않으면서도 오류라고 성급히 단정하지 않고, 답안 근거에 따라 객관적으로 진단한다. "
        "강점과 약점을 균형 있게 설명하고, 약점의 원인과 수정 필요성을 교육적인 언어로 전달한다. "
        "개선안은 권유와 지시의 중간 수준으로 제시하며 학생이 무엇을 어떻게 바꿔야 하는지 명확히 이해할 수 있어야 한다."
    ),
    "example_text": (
        "2번 항목에서 스마트폰 사용이 학습에 영향을 주지 않는다고 서술한 부분은 앞에서 언급한 집중력 문제와 뒤의 사용 감축 계획을 함께 고려하면 보완이 필요하다. "
        "현재 설명만으로는 사용 시간을 줄여야 하는 이유가 충분히 드러나지 않는다. "
        "스마트폰 사용으로 공부 시간이나 집중력이 실제로 어떻게 달라졌는지 구체적인 경험을 덧붙이면 글의 앞뒤 관계가 더 분명해질 것이다."
    ),
}


def seed_neutral_directness_preset(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.update_or_create(
        dimension="directness",
        level=PRESET["level"],
        defaults={
            "name": PRESET["name"],
            "prompt_rules": PRESET["prompt_rules"],
            "source_guide": PRESET["source_guide"],
            "example_text": PRESET["example_text"],
            "is_active": True,
            "version": 1,
        },
    )


def remove_neutral_directness_preset(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.filter(dimension="directness", level=3).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0012_seed_directness_tone_presets")]
    operations = [
        migrations.RunPython(
            seed_neutral_directness_preset,
            remove_neutral_directness_preset,
        )
    ]
