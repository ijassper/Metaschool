from django.db import migrations, models
from django.utils import timezone


def populate_page_date_and_order(apps, schema_editor):
    Page = apps.get_model('activities', 'CourseNotebookPage')
    current_group = None
    position = 0
    for page in Page.objects.order_by('notebook_id', 'student_id', 'section_id', 'created_at', 'id').iterator():
        group = (page.notebook_id, page.student_id, page.section_id)
        if group != current_group:
            current_group = group
            position = 0
        position += 1
        page.note_date = timezone.localtime(page.created_at).date() if page.created_at else None
        page.sort_order = position
        page.save(update_fields=['note_date', 'sort_order'])


class Migration(migrations.Migration):
    dependencies = [('activities', '0043_attendance_signature_workflow')]

    operations = [
        migrations.AddField(
            model_name='coursenotebookpage', name='note_date',
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name='노트 날짜'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage', name='sort_order',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='단원 내 순서'),
        ),
        migrations.RunPython(populate_page_date_and_order, migrations.RunPython.noop),
    ]
