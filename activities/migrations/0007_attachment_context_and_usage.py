from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activities', '0006_feedbackresult'),
    ]

    operations = [
        migrations.AddField(model_name='activityfile', name='content_hash', field=models.CharField(blank=True, db_index=True, max_length=64, verbose_name='파일 해시')),
        migrations.AddField(model_name='activityfile', name='extracted_at', field=models.DateTimeField(blank=True, null=True, verbose_name='추출 일시')),
        migrations.AddField(model_name='activityfile', name='extracted_char_count', field=models.PositiveIntegerField(default=0, verbose_name='추출 글자 수')),
        migrations.AddField(model_name='activityfile', name='extracted_text', field=models.TextField(blank=True, verbose_name='추출 텍스트')),
        migrations.AddField(model_name='activityfile', name='extraction_error', field=models.CharField(blank=True, max_length=500, verbose_name='추출 오류')),
        migrations.AddField(model_name='activityfile', name='extraction_status', field=models.CharField(choices=[('PENDING', '추출 대기'), ('READY', '추출 완료'), ('UNSUPPORTED', '미지원 형식'), ('ERROR', '추출 실패')], default='PENDING', max_length=16, verbose_name='텍스트 추출 상태')),
        migrations.CreateModel(
            name='ActivityAnalysisContext',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_fingerprint', models.CharField(db_index=True, max_length=64, verbose_name='원본 지문')),
                ('structured_context', models.TextField(blank=True, verbose_name='구조화된 활동 컨텍스트')),
                ('summary_text', models.TextField(blank=True, verbose_name='AI 분석용 요약본')),
                ('summary_model', models.CharField(blank=True, max_length=50, verbose_name='요약 모델')),
                ('summary_usage', models.JSONField(blank=True, default=dict, verbose_name='요약 토큰 사용량')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='생성 일시')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='갱신 일시')),
                ('activity', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='analysis_context_cache', to='activities.activity', verbose_name='활동')),
            ],
            options={'verbose_name': '활동 AI 컨텍스트 캐시', 'verbose_name_plural': '활동 AI 컨텍스트 캐시 목록'},
        ),
        migrations.CreateModel(
            name='AIUsageLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation', models.CharField(choices=[('ATTACHMENT_OCR', '첨부자료 OCR'), ('CONTEXT_SUMMARY', '활동 자료 요약'), ('STUDENT_ANALYSIS', '학생 답안 분석')], max_length=24, verbose_name='작업')),
                ('ai_model', models.CharField(max_length=50, verbose_name='AI 모델')),
                ('prompt_tokens', models.PositiveIntegerField(default=0, verbose_name='입력 토큰')),
                ('cached_tokens', models.PositiveIntegerField(default=0, verbose_name='캐시 입력 토큰')),
                ('completion_tokens', models.PositiveIntegerField(default=0, verbose_name='출력 토큰')),
                ('total_tokens', models.PositiveIntegerField(default=0, verbose_name='전체 토큰')),
                ('estimated_cost_usd', models.DecimalField(decimal_places=6, default=0, max_digits=12, verbose_name='예상 비용(USD)')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='사용 일시')),
                ('activity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_usage_logs', to='activities.activity', verbose_name='활동')),
                ('answer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_usage_logs', to='activities.answer', verbose_name='답안')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ai_usage_logs', to=settings.AUTH_USER_MODEL, verbose_name='교사')),
            ],
            options={'verbose_name': 'AI 토큰 사용 기록', 'verbose_name_plural': 'AI 토큰 사용 기록 목록', 'ordering': ['-created_at']},
        ),
        migrations.AddIndex(model_name='aiusagelog', index=models.Index(fields=['teacher', 'created_at'], name='ai_usage_teacher_idx')),
    ]
