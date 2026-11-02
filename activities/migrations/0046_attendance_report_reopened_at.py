from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0045_remove_attendance_folder_edit_policy'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancereport',
            name='reopened_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='교사 확정 취소 시각'),
        ),
    ]
