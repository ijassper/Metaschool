from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('activities', '0055_activity_proctor_capture_enabled')]

    operations = [
        migrations.CreateModel(
            name='AnswerRewriteDraft',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content_snapshot', models.JSONField(default=dict, verbose_name='고쳐쓰기 임시 내용')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='마지막 임시저장 시간')),
                ('answer', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='rewrite_draft', to='activities.answer', verbose_name='원본 답안')),
                ('base_revision', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='rewrite_drafts', to='activities.answersubmissionrevision', verbose_name='고쳐쓰기 기준 제출본')),
            ],
            options={'verbose_name': '고쳐쓰기 임시저장', 'verbose_name_plural': '고쳐쓰기 임시저장 목록'},
        ),
    ]
