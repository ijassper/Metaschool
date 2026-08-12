from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0008_persona_dimensions'),
        ('activities', '0005_update_typing_activity_choices'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeedbackResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_type', models.CharField(choices=[('grading', '채점/분석'), ('feedback', '피드백'), ('rewrite', '고쳐쓰기'), ('relay', '릴레이쓰기')], default='feedback', max_length=20, verbose_name='작업 유형')),
                ('feedback_content', models.TextField(verbose_name='AI 피드백 본문')),
                ('persona_used', models.JSONField(blank=True, default=dict, verbose_name='사용된 페르소나/어조 정보')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='저장 일시')),
                ('activity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback_results', to='activities.activity', verbose_name='활동')),
                ('answer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback_results', to='activities.answer', verbose_name='원본 답안')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback_results', to='accounts.student', verbose_name='학생')),
            ],
            options={
                'verbose_name': '학생 답안 작업 기록',
                'verbose_name_plural': '학생 답안 작업 기록 목록',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='feedbackresult',
            index=models.Index(fields=['answer', 'created_at'], name='feedback_answer_idx'),
        ),
    ]
