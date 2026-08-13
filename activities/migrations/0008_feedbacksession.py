from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activities', '0007_attachment_context_and_usage'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeedbackSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('feedback_title', models.CharField(blank=True, max_length=150, verbose_name='피드백 제목')),
                ('content', models.TextField(blank=True, verbose_name='피드백 본문')),
                ('options_snapshot', models.JSONField(blank=True, default=dict, verbose_name='생성 옵션 스냅샷')),
                ('version', models.PositiveIntegerField(verbose_name='버전')),
                ('status', models.CharField(choices=[('DRAFT', '임시 저장'), ('FINAL', '최종 저장')], default='DRAFT', max_length=10, verbose_name='저장 상태')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='생성 일시')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='수정 일시')),
                ('activity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback_sessions', to='activities.activity', verbose_name='활동')),
                ('answer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback_sessions', to='activities.answer', verbose_name='원본 답안')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback_sessions', to=settings.AUTH_USER_MODEL, verbose_name='작성 교사')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback_sessions', to='accounts.student', verbose_name='학생')),
            ],
            options={
                'verbose_name': 'AI 피드백 작업 세션',
                'verbose_name_plural': 'AI 피드백 작업 세션 목록',
                'ordering': ['-version', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='feedbacksession',
            constraint=models.UniqueConstraint(fields=('answer', 'version'), name='unique_feedback_session_version'),
        ),
        migrations.AddIndex(
            model_name='feedbacksession',
            index=models.Index(fields=['answer', '-version'], name='feedback_session_ver_idx'),
        ),
    ]
