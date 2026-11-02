from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0044_course_notebook_page_date_order'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='attendancereportfolder',
            name='allow_edit_after_submission',
        ),
    ]
