from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0028_activity_proctor_capture_scope'),
    ]

    operations = [
        migrations.AddField(
            model_name='proctorsession',
            name='android_version',
            field=models.CharField(blank=True, max_length=32, verbose_name='Android 버전'),
        ),
        migrations.AddField(
            model_name='proctorsession',
            name='app_version',
            field=models.CharField(blank=True, max_length=32, verbose_name='학생 앱 버전'),
        ),
        migrations.AddField(
            model_name='proctorsession',
            name='capture_scope',
            field=models.CharField(blank=True, max_length=20, verbose_name='감독 범위'),
        ),
        migrations.AddField(
            model_name='proctorsession',
            name='device_model',
            field=models.CharField(blank=True, max_length=100, verbose_name='기기 모델'),
        ),
    ]
