from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0041_attendance_reports'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancereportfolder',
            name='name',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='폴더명'),
        ),
        migrations.AddField(
            model_name='attendancereportfolder',
            name='operation_end_date',
            field=models.DateField(blank=True, null=True, verbose_name='운영 종료일'),
        ),
        migrations.AddField(
            model_name='attendancereportfolder',
            name='operation_start_date',
            field=models.DateField(blank=True, null=True, verbose_name='운영 시작일'),
        ),
    ]
