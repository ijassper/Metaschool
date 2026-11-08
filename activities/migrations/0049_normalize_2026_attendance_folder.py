from datetime import date

from django.db import migrations


FOLDER_ID = 1
OLD_START = date(2026, 10, 27)
OLD_END = date(2026, 11, 28)
NEW_START = date(2026, 3, 2)
NEW_END = date(2027, 2, 28)


def set_2026_academic_year(apps, schema_editor):
    Folder = apps.get_model('activities', 'AttendanceReportFolder')
    folders = Folder.objects.using(schema_editor.connection.alias)
    folder = folders.filter(pk=FOLDER_ID).first()
    if folder is None:
        return
    if (folder.academic_year, folder.operation_start_date, folder.operation_end_date) == (
        2026, NEW_START, NEW_END,
    ):
        return
    if (folder.academic_year, folder.operation_start_date, folder.operation_end_date) != (
        None, OLD_START, OLD_END,
    ):
        raise RuntimeError('기존 출결신고서 폴더의 학년도 또는 기간이 예상과 달라 자동 변경을 중단합니다.')
    if folders.filter(teacher_id=folder.teacher_id, academic_year=2026).exclude(pk=FOLDER_ID).exists():
        raise RuntimeError('담당 교사에게 2026학년도 폴더가 이미 있어 자동 변경을 중단합니다.')
    folders.filter(pk=FOLDER_ID).update(
        academic_year=2026,
        operation_start_date=NEW_START,
        operation_end_date=NEW_END,
    )


def restore_original_period(apps, schema_editor):
    Folder = apps.get_model('activities', 'AttendanceReportFolder')
    Folder.objects.using(schema_editor.connection.alias).filter(
        pk=FOLDER_ID,
        academic_year=2026,
        operation_start_date=NEW_START,
        operation_end_date=NEW_END,
    ).update(
        academic_year=None,
        operation_start_date=OLD_START,
        operation_end_date=OLD_END,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0048_attendance_folder_academic_year'),
    ]

    operations = [
        migrations.RunPython(set_2026_academic_year, restore_original_period),
    ]
