from django.db import migrations


FORMALITY_LEVEL_FOUR_RULES = (
    "젊은 교사가 교실에서 자연스럽게 말하듯 일상적 존댓말인 해요체를 모든 문장에 일관되게 사용하세요. "
    "허용 종결은 '했어요, 보여요, 인 것 같아요, 하면 좋겠어요, 해보면 어떨까요, 바라요, 응원할게요'입니다. "
    "'했어, 구나, 이야, 같아, 거든, 할게, 바라, 하자, 잘 지내' 같은 반말 종결은 절대 사용하지 마세요. "
    "학생의 주체성을 살리는 부드러운 제안형과 바로 실행할 수 있는 넛지형 조언을 사용하세요. "
    "성별 표현, 솔직성, 상세성, 첨삭 성격의 예시가 반말 종결을 포함하더라도 해당 종결은 무시하고 반드시 해요체로 변환하세요. "
    "출력 전에 모든 문장 종결을 검사하여 반말이 남아 있으면 자연스러운 해요체로 고치세요."
)

FORMALITY_LEVEL_FOUR_SOURCE = (
    "예의 갖춤 1단계는 젊은 교사가 학생에게 자연스럽고 다정하게 건네는 일상적 해요체다. 문장 종결과 존댓말 여부는 형식성 축이 독점적으로 결정한다. "
    "다른 어조 축은 어휘와 전달 전략만 제공하며 종결어미에는 관여하지 않는다. 전체 결과에서 반말과 해요체가 섞이지 않도록 최종 점검한다."
)

FORMALITY_LEVEL_FOUR_EXAMPLE = (
    "은채 학생, 반가워요! 이번에 작성한 글을 꼼꼼하게 읽어보았어요. 자신의 생각을 솔직하게 정리한 점이 인상 깊었어요. "
    "주장의 이유를 조금 더 구체적으로 설명하면 독자가 훨씬 쉽게 이해할 수 있을 것 같아요. 다음 글에서도 생각을 차근차근 발전시켜 보길 바라요. 응원할게요!"
)

GENDER_SUFFIX_RULE = (
    " 문장의 종결어미와 존댓말·반말 여부는 형식성 프리셋만 결정합니다. 이 프리셋은 감정선과 어휘 선택에만 적용하고, 예시의 종결어미가 형식성과 충돌하면 사용하지 마세요."
)


def enforce_formality_priority(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.update_or_create(
        dimension="formality",
        level=4,
        defaults={
            "name": "일상적 존댓말·친절한 해요체",
            "prompt_rules": FORMALITY_LEVEL_FOUR_RULES,
            "source_guide": FORMALITY_LEVEL_FOUR_SOURCE,
            "example_text": FORMALITY_LEVEL_FOUR_EXAMPLE,
            "is_active": True,
            "version": 2,
        },
    )
    for preset in ToneStylePreset.objects.filter(dimension="gender", level__in=[1, 2]):
        if GENDER_SUFFIX_RULE.strip() not in preset.prompt_rules:
            preset.prompt_rules = preset.prompt_rules.rstrip() + GENDER_SUFFIX_RULE
            preset.version = max(preset.version, 2)
            preset.save(update_fields=["prompt_rules", "version"])


def restore_previous_versions(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.filter(dimension="formality", level=4).update(version=1)
    for preset in ToneStylePreset.objects.filter(dimension="gender", level__in=[1, 2]):
        preset.prompt_rules = preset.prompt_rules.replace(GENDER_SUFFIX_RULE, "")
        preset.version = 1
        preset.save(update_fields=["prompt_rules", "version"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0020_refine_formal_student_address_rules")]
    operations = [migrations.RunPython(enforce_formality_priority, restore_previous_versions)]
