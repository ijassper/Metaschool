from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0008_feedbacksession'),
    ]

    operations = [
        migrations.AlterField(
            model_name='activity',
            name='q1_title',
            field=models.TextField(default='항목 1', verbose_name='문항 1 제목'),
        ),
        migrations.AlterField(
            model_name='activity',
            name='q2_title',
            field=models.TextField(default='항목 2', verbose_name='문항 2 제목'),
        ),
        migrations.AlterField(
            model_name='activity',
            name='q3_title',
            field=models.TextField(default='항목 3', verbose_name='문항 3 제목'),
        ),
    ]
