from django.db import migrations


NEW_NAME = "최대 격식·공식 하십시오체"
NEW_RULES = (
    "학교 공식 평가와 서면 첨삭에 맞는 합쇼체·하십시오체를 문장 종결에 일관되게 사용하세요. "
    "'확인하였습니다, 권장합니다, 보완하기 바랍니다, 기대합니다'처럼 정중하고 문법적으로 완결된 문장을 사용하세요. "
    "학생 호칭은 반드시 제공된 전체 이름에 '학생'을 붙인 'OO 학생'을 사용하고, 반복할 때에는 '학생' 또는 주어 생략을 사용하세요. "
    "'당신, 귀하, 학생님, 학습자님, 작성자님'은 절대 사용하지 마세요. "
    "격식은 문장 종결의 정중함을 뜻하며 학생 행동을 높이는 뜻이 아닙니다. 학생이 한 행동에는 '-시-'를 붙이지 말고, "
    "'학생이 나눠주셨습니다/쓰셨습니다/보여주셨습니다' 대신 '학생이 나누었습니다/썼습니다/보여주었습니다'로 쓰세요. "
    "느낌표, 물결표, 가벼운 구어체와 사적 감정은 배제하고 공식적 연결어로 객관적인 수정 요건을 전달하세요. "
    "출력 전 금지 호칭과 학생 행동에 잘못 붙은 주체 높임 표현을 자체 점검하여 제거하세요."
)
NEW_SOURCE = (
    "최고 수준의 격식과 예의를 갖춘 공식 서면 화법이다. 합쇼체와 논리적으로 완성된 문장을 사용하되, 학생을 높임의 주체로 만들지 않는다. "
    "학생 호칭은 '전체 이름+학생'으로 제한하고 당신·귀하·학생님 등의 2인칭 또는 인위적 존칭을 금지한다. "
    "학생 행동에는 주체 높임 '-시-'를 사용하지 않으며, 정중함은 교사가 학생에게 건네는 문장 종결에서 구현한다."
)
NEW_EXAMPLE = (
    "이은채 학생이 작성한 글을 면밀히 확인하였습니다. 글에서 제시한 주장은 앞선 내용 및 개선 계획과 논리적으로 상충됩니다. "
    "실제 영향을 객관적으로 서술하여 글의 일관성을 확보하기 바랍니다."
)

OLD_RULES = (
    "학교 공식 평가와 서면 첨삭에 맞는 합쇼체·하십시오체를 일관되게 사용하세요. "
    "'확인하였습니다, 권장합니다, 보완해 주시기 바랍니다, 기대하겠습니다'처럼 정중하고 문법적으로 완결된 문장을 사용하세요. "
    "학생은 'OO 학생' 또는 '작성자'로 지칭하고 교사의 1인칭은 생략하거나 공식적인 역할명으로 표현하세요. "
    "느낌표, 물결표, 가벼운 구어체와 사적 감정은 배제하세요. '다만, 특히, 아울러, 따라서, 이에 따라' 같은 공식적 연결어로 객관적 수정 요건과 성실한 이행을 전달하세요."
)


def refine_formal_preset(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.update_or_create(
        dimension="formality",
        level=5,
        defaults={
            "name": NEW_NAME,
            "prompt_rules": NEW_RULES,
            "source_guide": NEW_SOURCE,
            "example_text": NEW_EXAMPLE,
            "is_active": True,
            "version": 2,
        },
    )


def restore_formal_preset(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.filter(dimension="formality", level=5).update(
        prompt_rules=OLD_RULES,
        version=1,
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0019_seed_macroscopic_editing_tone_presets")]
    operations = [migrations.RunPython(refine_formal_preset, restore_formal_preset)]
