from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0046_attendance_report_reopened_at'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='attendancereport',
            name='unique_attendance_report_per_student_folder',
        ),
    ]
