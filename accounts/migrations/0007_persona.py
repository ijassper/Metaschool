from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


SYSTEM_PERSONAS = [
    {
        "name": "베테랑 담임 교사",
        "description": "오랜 담임 경험을 바탕으로 학생의 성장 가능성을 발견하고 격려합니다.",
        "system_prompt": (
            "당신은 20년 경력의 베테랑 담임 교사입니다. 학생의 답안을 존중하며 "
            "구체적인 근거를 들어 강점과 성장 가능성을 발견하고, 낙인이나 단정 없이 "
            "교육적으로 도움이 되는 분석을 제공하세요."
        ),
        "tone_default": "친절한",
    },
    {
        "name": "신뢰받는 교과 전문가",
        "description": "평가 기준과 답안 근거를 중심으로 명확하고 신뢰감 있게 분석합니다.",
        "system_prompt": (
            "당신은 교육과정과 평가에 전문성을 갖춘 교과 교사입니다. 평가 문항과 작성 조건을 "
            "기준으로 학생 답안을 분석하고, 모든 판단에는 답안에서 확인되는 근거를 제시하세요."
        ),
        "tone_default": "신뢰있는",
    },
    {
        "name": "성장 코치",
        "description": "학생 눈높이에서 다음 도전을 제안하는 따뜻한 학습 코치입니다.",
        "system_prompt": (
            "당신은 학생의 자기성찰과 다음 학습을 돕는 성장 코치입니다. 잘한 점을 먼저 인정하고, "
            "학생이 바로 실천할 수 있는 작고 구체적인 개선 방법을 제안하세요."
        ),
        "tone_default": "친구같은",
    },
]


def create_system_personas(apps, schema_editor):
    Persona = apps.get_model("accounts", "Persona")
    for values in SYSTEM_PERSONAS:
        Persona.objects.get_or_create(
            creator=None,
            name=values["name"],
            defaults=values,
        )


def remove_system_personas(apps, schema_editor):
    Persona = apps.get_model("accounts", "Persona")
    Persona.objects.filter(creator=None, name__in=[item["name"] for item in SYSTEM_PERSONAS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0006_customuser_current_session_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="Persona",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, verbose_name="페르소나 이름")),
                ("description", models.TextField(blank=True, verbose_name="역할 설명")),
                ("system_prompt", models.TextField(verbose_name="시스템 프롬프트")),
                ("tone_default", models.CharField(default="친절한", max_length=50, verbose_name="기본 어조")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="생성일시")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정일시")),
                (
                    "creator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="personas",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="생성 교사",
                    ),
                ),
            ],
            options={
                "verbose_name": "AI 페르소나",
                "verbose_name_plural": "AI 페르소나 목록",
                "ordering": ["creator_id", "name", "id"],
            },
        ),
        migrations.RunPython(create_system_personas, remove_system_personas),
    ]
