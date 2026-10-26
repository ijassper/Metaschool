from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0021_enforce_formality_axis_priority'),
        ('activities', '0040_course_notebook_page_processing_metadata'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceReportFolder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allow_edit_after_submission', models.BooleanField(default=True, verbose_name='제출 후 수정 허용')),
                ('is_active', models.BooleanField(default=True, verbose_name='사용 여부')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('target_students', models.ManyToManyField(blank=True, related_name='attendance_report_folders', to='accounts.student', verbose_name='대상 학생')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_report_folders', to=settings.AUTH_USER_MODEL, verbose_name='담당 교사')),
            ],
            options={
                'verbose_name': '출결 신고서 폴더',
                'verbose_name_plural': '출결 신고서 폴더 목록',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['teacher', 'is_active'], name='attendance_folder_teacher_idx')],
            },
        ),
        migrations.CreateModel(
            name='AttendanceReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attendance_type', models.CharField(choices=[('SICK_TARDY', '질병지각'), ('SICK_RESULT', '질병결과'), ('SICK_LEAVE', '질병조퇴'), ('SICK_ABSENCE', '질병결석')], max_length=20, verbose_name='출결명')),
                ('start_date', models.DateField(verbose_name='출결 시작일')),
                ('end_date', models.DateField(blank=True, null=True, verbose_name='출결 종료일')),
                ('start_period', models.CharField(blank=True, choices=[('HOMEROOM', '조회'), ('1', '1교시'), ('2', '2교시'), ('3', '3교시'), ('4', '4교시'), ('5', '5교시'), ('6', '6교시'), ('7', '7교시'), ('8', '8교시'), ('9', '9교시'), ('10', '10교시'), ('CLOSING', '종례')], max_length=12, verbose_name='시작 교시')),
                ('end_period', models.CharField(blank=True, choices=[('HOMEROOM', '조회'), ('1', '1교시'), ('2', '2교시'), ('3', '3교시'), ('4', '4교시'), ('5', '5교시'), ('6', '6교시'), ('7', '7교시'), ('8', '8교시'), ('9', '9교시'), ('10', '10교시'), ('CLOSING', '종례')], max_length=12, verbose_name='종료 교시')),
                ('reason', models.TextField(max_length=1000, verbose_name='출결 사유')),
                ('written_date', models.DateField(verbose_name='작성 날짜')),
                ('student_signature', models.CharField(max_length=100, verbose_name='학생 서명')),
                ('guardian_signature', models.CharField(max_length=100, verbose_name='보호자 서명')),
                ('submitted_at', models.DateTimeField(blank=True, null=True, verbose_name='제출 시각')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('folder', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='activities.attendancereportfolder', verbose_name='출결 신고서 폴더')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_reports', to='accounts.student', verbose_name='학생')),
            ],
            options={
                'verbose_name': '출결 확인 신고서',
                'verbose_name_plural': '출결 확인 신고서 목록',
                'ordering': ['-submitted_at', '-updated_at'],
                'indexes': [models.Index(fields=['folder', 'submitted_at'], name='attendance_report_folder_idx')],
                'constraints': [models.UniqueConstraint(fields=('folder', 'student'), name='unique_attendance_report_per_student_folder')],
            },
        ),
    ]
