from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0047_allow_multiple_attendance_reports'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancereportfolder',
            name='academic_year',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='학년도'),
        ),
        migrations.AddConstraint(
            model_name='attendancereportfolder',
            constraint=models.UniqueConstraint(
                fields=('teacher', 'academic_year'),
                name='unique_attendance_folder_teacher_year',
            ),
        ),
    ]
