from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('activities', '0027_proctor_sessions_and_events')]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='proctor_capture_scope',
            field=models.CharField(
                choices=[
                    ('FULL_DISPLAY', '전체 화면 감독'),
                    ('APP_ONLY', '인그리드 앱만 감독'),
                ],
                default='FULL_DISPLAY',
                max_length=20,
                verbose_name='감독 녹화 범위',
            ),
        ),
    ]
