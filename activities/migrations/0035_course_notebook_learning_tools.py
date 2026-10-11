from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0034_alter_answerdraftrevision_save_reason'),
    ]

    operations = [
        migrations.CreateModel(
            name='CourseNotebookMaterial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='course_notebook_materials/%Y/%m/%d/', verbose_name='교재 파일')),
                ('original_name', models.CharField(max_length=255, verbose_name='원본 파일명')),
                ('content_type', models.CharField(blank=True, max_length=120, verbose_name='MIME 유형')),
                ('size', models.PositiveBigIntegerField(default=0, verbose_name='파일 크기')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('notebook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='materials', to='activities.coursenotebook', verbose_name='교과 수업 노트')),
            ],
            options={'verbose_name': '수업 노트 교재', 'verbose_name_plural': '수업 노트 교재 목록', 'ordering': ['created_at', 'id']},
        ),
        migrations.CreateModel(
            name='CourseNotebookSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=100, verbose_name='단원명')),
                ('depth', models.PositiveSmallIntegerField(default=0, verbose_name='깊이')),
                ('position', models.PositiveIntegerField(default=0, verbose_name='표시 순서')),
                ('notebook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='activities.coursenotebook', verbose_name='교과 수업 노트')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='activities.coursenotebooksection', verbose_name='상위 단원')),
            ],
            options={'verbose_name': '수업 노트 단원', 'verbose_name_plural': '수업 노트 단원 목록', 'ordering': ['position', 'id']},
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='section',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pages', to='activities.coursenotebooksection', verbose_name='단원'),
        ),
        migrations.CreateModel(
            name='CourseNotebookStickyNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField(blank=True, max_length=1000, verbose_name='메모')),
                ('x', models.DecimalField(decimal_places=2, default=8, max_digits=5, verbose_name='X 위치(%)')),
                ('y', models.DecimalField(decimal_places=2, default=8, max_digits=5, verbose_name='Y 위치(%)')),
                ('width', models.DecimalField(decimal_places=2, default=32, max_digits=5, verbose_name='너비(%)')),
                ('height', models.DecimalField(decimal_places=2, default=24, max_digits=5, verbose_name='높이(%)')),
                ('color', models.CharField(choices=[('YELLOW', '노랑'), ('PINK', '분홍'), ('BLUE', '파랑'), ('GREEN', '초록')], default='YELLOW', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('page', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sticky_notes', to='activities.coursenotebookpage', verbose_name='노트 페이지')),
            ],
            options={'verbose_name': '수업 노트 포스트잇', 'verbose_name_plural': '수업 노트 포스트잇 목록', 'ordering': ['created_at', 'id']},
        ),
        migrations.AddIndex(
            model_name='coursenotebooksection',
            index=models.Index(fields=['notebook', 'position'], name='course_section_order_idx'),
        ),
    ]
