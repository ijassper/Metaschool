from django.db import migrations


PRESET = {
    "name": "균형 잡힌 진단·객관적 건설형",
    "prompt_rules": (
        "단도직입적인 오류 지적과 우회적인 질문·완곡한 유도의 중간 수준을 유지하세요. "
        "부족한 점을 가치 판단 없이 객관적으로 짚고, 어떤 부분이 왜 자연스럽지 못한지 글의 전체 맥락과 근거를 들어 차분히 설명하세요. "
        "'모순이다' 같은 단정이나 '아쉽다' 같은 주관적 감정보다 '논리적 연결이 다소 매끄럽지 않다, 보완의 여지가 있다, 보완이 필요하다'처럼 중립적으로 진단하세요. "
        "개선안은 명령형이나 수사적 질문을 피하고 '할 필요가 있다, 하는 것이 좋다, 구체적으로 서술하면 완성도가 높아질 것이다' 같은 표준적인 권유형으로 제시하세요. "
        "칭찬은 과장하지 말고 글에서 확인되는 긍정적인 면과 실천적 가치를 근거와 함께 균형 있게 설명하세요. "
        "학생의 인격이 아닌 답안의 내용과 표현만 평가하세요."
    ),
    "source_guide": (
        "솔직성 축의 중립 기준점으로, 글의 부족한 점을 가치 판단 없이 객관적으로 짚고 실천 가능한 보완 방안을 담담하게 제시한다. "
        "비난이나 질책 없이도 문제를 감추지 않으며, 객관적 서술, 이유 중심의 설명, 표준적인 권유형 제안을 핵심으로 한다. "
        "직접적인 '모순이다·틀렸다'와 주관적인 '아쉽다', 과도한 질문형 유도를 피한다. "
        "강점은 긍정적인 면과 실천적 가치를 균형 있게 명시한다. 약점은 앞뒤 맥락에서 연결이 부족한 이유를 설명하고, "
        "개선 방향은 구체적인 경험이나 근거를 추가하도록 안내하여 글의 완성도를 높인다."
    ),
    "example_text": (
        "2번 항목에서 '스마트폰 사용이 나의 학습에 딱히 영향을 끼치지 않는다'고 서술한 부분은 보완이 필요하다. "
        "1번에서 과다 사용의 문제점을 짚고 4번에서 사용 시간 감축을 결심한 흐름에 비추어 볼 때, 2번의 내용은 앞뒤 맥락과 자연스럽게 이어지지 않는 면이 있다. "
        "하루 6~7시간의 스마트폰 사용이 실제 학습 집중도나 시간 관리에 미친 영향을 솔직하게 연결하여 서술하는 것이 좋다. "
        "실제 영향을 구체적으로 기술한다면 4번에서 제시한 실천 계획의 타당성이 더욱 잘 뒷받침될 것이다."
    ),
}


def refine_neutral_directness_preset(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.update_or_create(
        dimension="directness",
        level=3,
        defaults={
            **PRESET,
            "is_active": True,
            "version": 2,
        },
    )


def restore_previous_neutral_directness_preset(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.filter(dimension="directness", level=3).update(version=1)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_seed_neutral_directness_tone_preset")]
    operations = [
        migrations.RunPython(
            refine_neutral_directness_preset,
            restore_previous_neutral_directness_preset,
        )
    ]
