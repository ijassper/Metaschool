from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('activities', '0054_activity_force_open')]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='proctor_capture_enabled',
            field=models.BooleanField(default=True, verbose_name='감독 화면 수신 허용'),
        ),
    ]
