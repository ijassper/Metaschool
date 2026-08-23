from django.db import migrations


PRESETS = [
    {
        "level": 4,
        "name": "문단 구성·논리 흐름 점검형",
        "prompt_rules": (
            "오탈자와 띄어쓰기 같은 표면 교정은 지양하고 문단 사이의 논리적 연결, 주장의 일관성, 근거의 타당성과 글의 전체 흐름을 중심으로 첨삭하세요. "
            "각 문항이나 문단이 문제 인식→현황 분석→목표 또는 각오→실천 계획으로 자연스럽게 이어지는지 확인하고, 주장과 근거 및 문제와 해결책 사이의 인과관계를 진단하세요. "
            "강점은 체계적인 구성과 논리 전개를, 약점은 문단 사이의 불일치나 인과적 단절을 실제 답안 근거로 밝히세요. "
            "개선 방향은 핵심 주장을 재배치하거나 빠진 연결 내용을 보완하는 구조적 가이드로 제시하고, 맞춤법이나 개별 어휘는 전체 의미를 방해하는 예외적인 경우가 아니면 언급하지 마세요. "
            "구조 분석의 깊이는 유지하되 출력 어휘와 문장 복잡성은 별도로 지정된 학교급 기준을 따르세요."
        ),
        "source_guide": (
            "거시적 1단계는 문단 구성과 논리 전개 중심의 구조적 흐름 점검형이다. 개별 문장의 표기보다 문단 간 연결성, 주장 일관성과 근거 타당성을 진단한다. "
            "목표와 실천 계획이 앞의 문제 분석과 유기적으로 이어지는지 살피고, 문단 사이의 내용 불일치와 문제·해결책 사이의 인과 단절을 지적한다. "
            "개선안은 글의 흐름이 끊기지 않도록 문단의 핵심 주장을 재정렬하고 필요한 연결 내용을 보완하는 방향으로 제시한다."
        ),
        "example_text": (
            "2번에서 학습 영향이 없다고 서술한 부분은 글 전체의 흐름을 깨뜨린다. 1번에서 과다 사용의 위험을 인식하고 4번에서 시간 감축 계획을 세웠지만, 2번에서 부정적 영향을 부인하여 문제 진단과 해결 방안 사이의 연결이 끊어졌다. "
            "2번에 실제 학습 손실과 집중력 저하를 명확히 적어야 3번의 각오와 4번의 계획이 설득력 있는 하나의 구조로 이어진다."
        ),
    },
    {
        "level": 5,
        "name": "최대 거시·전체 구조 총괄형",
        "prompt_rules": (
            "맞춤법, 띄어쓰기, 어휘와 개별 문장 표현은 다루지 말고 글 전체의 핵심 메시지, 대주제 부합성, 서사적 완결성과 문제 해결 구조만 총괄적으로 평가하세요. "
            "글이 문제 인식→현상 진단→목표 설정→실천→점검의 전체 논리 체계를 갖추고 하나의 중심 주제로 수렴하는지 분석하세요. "
            "강점은 글 전체의 기획력과 구성력 및 중심 주제를 실천 체계로 확장한 방식을 평가하고, 약점은 진단과 해결책 사이의 구조적 모순처럼 전체 설계를 흔드는 핵심 결함만 제시하세요. "
            "개선 방향은 핵심 논점과 문단 역할을 재설계하여 글의 거시적 뼈대와 인과관계를 완성하는 데 집중하세요. "
            "미시적 오류는 일절 나열하지 말고, '프레임워크, 정합성' 같은 추상 용어를 학생에게 그대로 남발하지 않으며 학교급에 맞는 쉬운 표현으로 풀어 쓰세요."
        ),
        "source_guide": (
            "거시적 2단계는 최대 거시 첨삭이다. 개별 문장 오류를 배제하고 대주제 부합도, 전체 메시지, 서사적 완결성과 문제 해결 체계의 타당성을 평가한다. "
            "문제 인식, 현상 진단, 목표 설정, 실천 및 환류로 이어지는 전체 구조가 완결되는지 확인한다. 강점은 글 전체의 기획력, 약점은 전체 설계를 무너뜨리는 핵심 모순, 개선안은 중심 논리 축과 글의 뼈대를 재설계하는 방향으로 제시한다."
        ),
        "example_text": (
            "글의 전체 구조에서 2번 문단이 논리적 공백을 만든다. 문제 인식, 현황 진단, 비전 수립, 해결책 실행으로 이어져야 하지만 진단 단계에서 부정적 영향을 부인하여 뒤의 실천 계획이 필요한 이유가 약해졌다. "
            "글 전체를 '문제를 정확히 바라보고 진로와 연결한 해결책을 실천한다'는 하나의 흐름으로 다시 정리하고, 2번에서 과다 사용의 실제 영향을 분명히 밝혀 진단과 해결책을 연결해야 한다."
        ),
    },
]


def seed_macroscopic_editing_presets(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    for preset in PRESETS:
        ToneStylePreset.objects.update_or_create(
            dimension="editing",
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


def remove_macroscopic_editing_presets(apps, schema_editor):
    ToneStylePreset = apps.get_model("accounts", "ToneStylePreset")
    ToneStylePreset.objects.filter(dimension="editing", level__in=[4, 5]).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0018_seed_microscopic_editing_tone_presets")]
    operations = [migrations.RunPython(seed_macroscopic_editing_presets, remove_macroscopic_editing_presets)]
