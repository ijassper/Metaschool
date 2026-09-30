import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0032_course_notebook_and_rename_scratchpad'),
        ('accounts', '0003_backfill_student_school'),
    ]

    operations = [
        migrations.CreateModel(
            name='CourseNotebookPage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.FileField(upload_to='course_notebooks/%Y/%m/%d/', verbose_name='노트 이미지')),
                ('memo', models.CharField(blank=True, max_length=200, verbose_name='한 줄 메모')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('notebook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pages', to='activities.coursenotebook', verbose_name='교과 수업 노트')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='course_notebook_pages', to='accounts.student', verbose_name='학생')),
            ],
            options={
                'verbose_name': '교과 수업 노트 페이지',
                'verbose_name_plural': '교과 수업 노트 페이지 목록',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='coursenotebookpage',
            index=models.Index(fields=['notebook', 'student', '-created_at'], name='course_page_lookup_idx'),
        ),
    ]
