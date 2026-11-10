from django.db import migrations, models
import django.db.models.deletion


def assign_existing_numbers(apps, schema_editor):
    Report = apps.get_model('activities', 'AttendanceReport')
    Sequence = apps.get_model('activities', 'AttendanceReportSequence')
    alias = schema_editor.connection.alias
    counts = {}
    reports = Report.objects.using(alias).select_related('student', 'folder').order_by('created_at', 'id')
    for report in reports.iterator():
        year = report.folder.academic_year or report.start_date.year
        key = (report.student_id, year)
        counts[key] = counts.get(key, 0) + 1
        student = report.student
        report.report_number = (
            f'{year}-{student.grade}-{student.class_no:02d}-'
            f'{student.number:02d}-{counts[key]:02d}'
        )
        report.save(update_fields=['report_number'])
    for (student_id, year), last_number in counts.items():
        Sequence.objects.using(alias).create(
            student_id=student_id, academic_year=year, last_number=last_number,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0049_normalize_2026_attendance_folder'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancereport',
            name='report_number',
            field=models.CharField(blank=True, default='', max_length=40, verbose_name='신고서 고유번호'),
        ),
        migrations.CreateModel(
            name='AttendanceReportSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('academic_year', models.PositiveSmallIntegerField()),
                ('last_number', models.PositiveIntegerField(default=0)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.student')),
            ],
            options={
                'constraints': [models.UniqueConstraint(
                    fields=('student', 'academic_year'), name='unique_attendance_report_sequence',
                )],
            },
        ),
        migrations.RunPython(assign_existing_numbers, migrations.RunPython.noop),
    ]
