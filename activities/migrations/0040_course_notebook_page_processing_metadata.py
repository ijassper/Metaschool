from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0039_course_notebook_page_ocr_structure'),
    ]

    operations = [
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_usage',
            field=models.JSONField(blank=True, default=dict, verbose_name='OCR 사용량과 비용'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='source_hash',
            field=models.CharField(blank=True, db_index=True, max_length=64, verbose_name='원본 이미지 해시'),
        ),
    ]
