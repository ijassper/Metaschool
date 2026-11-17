from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('activities', '0053_activity_teacher_pause')]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='is_force_open',
            field=models.BooleanField(default=False, verbose_name='교사 수동 개방 여부'),
        ),
    ]
