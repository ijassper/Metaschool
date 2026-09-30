from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0029_proctorsession_device_diagnostics'),
    ]

    operations = [
        migrations.AddField(
            model_name='proctorsession',
            name='security_status',
            field=models.CharField(
                choices=[
                    ('UNKNOWN', '확인 중'),
                    ('SECURE', '보안 정상'),
                    ('PINNING_RELEASED', '화면 고정 해제'),
                    ('NOT_REQUIRED', '화면 고정 미적용'),
                ],
                default='UNKNOWN',
                max_length=24,
                verbose_name='보안 상태',
            ),
        ),
        migrations.AddField(
            model_name='proctorsession',
            name='security_updated_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='보안 상태 확인 시각'),
        ),
        migrations.AlterField(
            model_name='proctorevent',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('CAPTURE_STARTED', '녹화 시작'),
                    ('APP_BACKGROUND', '앱 이탈'),
                    ('APP_FOREGROUND', '앱 복귀'),
                    ('CAPTURE_STOPPED', '녹화 중단'),
                    ('EXAM_ENDED', '시험 종료'),
                    ('ERROR', '오류'),
                    ('SECURITY_ACTIVE', '보안 정상'),
                    ('PINNING_RELEASED', '화면 고정 해제'),
                    ('SECURITY_NOT_REQUIRED', '화면 고정 미적용'),
                ],
                max_length=30,
            ),
        ),
    ]
